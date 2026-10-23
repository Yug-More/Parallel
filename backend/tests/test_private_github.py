from dataclasses import replace
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from test_collaboration import join, project
from test_intelligence import detail, drain, start
from test_native_actions import approve, proposal

import github_app
from actions import execute_once
from models import (
    GitHubAuthorization,
    ImportedRecord,
    RepositoryConnection,
    RepositorySync,
    utc_now,
)
from repositories import SyncError, sync_once


def configure(app):
    app.state.settings = replace(
        app.state.settings,
        github_connector_enabled=True,
        github_app_enabled=True,
        github_app_id=123,
        github_app_client_id="fixture-client-id",
        github_app_client_secret="fixture-client-secret",
        credential_encryption_key=Fernet.generate_key().decode(),
    )


def transport(path, *, token=None, data=None):
    if path == "/login/device/code":
        return {
            "device_code": "fixture-device-only",
            "user_code": "ABCD-EFGH",
            "expires_in": 900,
            "interval": 5,
        }
    if path == "/login/oauth/access_token":
        return {
            "token_type": "bearer",
            "access_token": "fixture-access-only",
            "refresh_token": "fixture-refresh-only",
            "expires_in": 28800,
        }
    assert token == "fixture-access-only"
    if path.startswith("/user/installations?"):
        return {
            "installations": [
                {
                    "id": 42,
                    "app_id": 123,
                    "repository_selection": "selected",
                    "permissions": {"metadata": "read", "issues": "read", "pull_requests": "read"},
                }
            ]
        }
    if path.startswith("/user/installations/42/repositories?"):
        return {"repositories": [{"id": 99, "full_name": "org/private"}]}
    if path == "/repos/org/private":
        return {
            "id": 99,
            "private": True,
            "full_name": "org/private",
            "description": "Private roadmap",
        }
    if "/issues?" in path:
        return [
            {
                "number": 1,
                "title": "Review authentication blocker",
                "body": "Session issue blocks release",
                "state": "open",
            }
        ]
    if "/pulls?" in path:
        return []
    raise AssertionError(path)


def authorize(owner, wid, app):
    response = owner.post(
        f"/workspaces/{wid}/github-authorizations",
        json={"repository": "org/private", "installation_id": 42},
    )
    assert response.status_code == 202, response.text
    value = response.json()
    assert (
        "device_code" not in response.text
        and value["verification_uri"] == "https://github.com/login/device"
    )
    with app.state.session_factory() as db:
        row = db.get(GitHubAuthorization, value["id"])
        assert "fixture-device" not in row.device_secret
        row.next_poll_at = utc_now() - timedelta(seconds=1)
        db.commit()
    response = owner.post(f"/workspaces/{wid}/github-authorizations/{value['id']}/complete")
    assert response.status_code == 200, response.text
    return response.json()


def test_private_device_authorization_sync_triage_receipt_and_revoke(
    accounts, application, monkeypatch
):
    configure(application)
    monkeypatch.setattr(github_app, "request_json", transport)
    owner, _ = accounts()
    member, _ = accounts("member@example.test", "Member")
    wid = project(owner)
    join(owner, member, wid, "member@example.test")
    assert (
        member.post(
            f"/workspaces/{wid}/github-authorizations",
            json={"repository": "org/private", "installation_id": 42},
        ).status_code
        == 403
    )
    result = authorize(owner, wid, application)
    assert result["state"] == "completed"
    connection = result["connection"]
    assert connection["auth_mode"] == "github_app_user" and "credential" not in connection
    factory = application.state.session_factory
    assert sync_once(factory, settings=application.state.settings)
    source = owner.get(f"/workspaces/{wid}/knowledge?kind=external&q=authentication").json()[
        "items"
    ][0]
    with factory() as db:
        row = db.get(RepositoryConnection, connection["id"])
        assert "fixture-access" not in row.credential
        assert db.query(GitHubAuthorization).one().device_secret is None
        row.credential_expires_at = utc_now() - timedelta(seconds=1)
        job = db.query(RepositorySync).one()
        job.state, job.next_attempt_at = "queued", utc_now()
        db.commit()
    assert sync_once(factory, settings=application.state.settings)  # renewal
    run = start(owner, wid, agent_type="local.delivery.v1", objective="triage github issues")
    drain(application)
    assert detail(owner, wid, run)["state"] == "completed"
    item = proposal(owner, wid)
    assert (
        item["payload"]["proposal"]["tasks"][0]["title"]
        == "Review issue: Review authentication blocker"
    )
    assert "external:" in item["payload"]["proposal"]["tasks"][0]["description"]
    assert approve(owner, wid, item).status_code == 200
    assert execute_once(factory)
    assert proposal(owner, wid)["state"] == "executed"
    assert (
        owner.post(
            f"/workspaces/{wid}/connections/{connection['id']}/revoke", json={"version": 1}
        ).status_code
        == 200
    )
    assert member.get(f"/workspaces/{wid}/sources/external/{source['id']}").status_code == 404
    with factory() as db:
        assert db.get(RepositoryConnection, connection["id"]).credential is None


def test_private_authority_expiry_hides_derived_answers_and_sources(
    accounts, application, monkeypatch
):
    configure(application)
    monkeypatch.setattr(github_app, "request_json", transport)
    owner, _ = accounts()
    wid = project(owner)
    connection = authorize(owner, wid, application)["connection"]
    factory = application.state.session_factory
    sync_once(factory, settings=application.state.settings)
    answer = owner.post(
        f"/workspaces/{wid}/answers",
        json={"question": "authentication blocker", "idempotency_key": "private-answer-one"},
    ).json()
    assert answer["claims"]
    with factory() as db:
        db.get(RepositoryConnection, connection["id"]).access_verified_until = (
            utc_now() - timedelta(seconds=1)
        )
        db.commit()
    assert owner.get(f"/workspaces/{wid}/knowledge?kind=external").json()["total"] == 0
    assert (
        owner.get(f"/workspaces/{wid}/answers").json()["items"][0]["state"]
        == "evidence_unavailable"
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ("write", "read_only_permissions_required"),
        ("all", "selected_installation_required"),
        ("other-app", "selected_installation_required"),
        ("missing", "repository_access_lost"),
    ],
)
def test_private_permission_verification_rejects_broad_or_unavailable_grants(
    application, change, code
):
    configure(application)

    def read(path, **kwargs):
        value = transport(path, **kwargs)
        if path.startswith("/user/installations?"):
            row = value["installations"][0]
            if change == "write":
                row["permissions"]["issues"] = "write"
            if change == "all":
                row["repository_selection"] = "all"
            if change == "other-app":
                row["app_id"] = 999
        elif change == "missing":
            value = {"repositories": []}
        return value

    with pytest.raises(SyncError) as exc:
        github_app.verified_repository(
            application.state.settings, "fixture-access-only", 42, "org/private", read
        )
    assert exc.value.code == code


def test_private_access_loss_cancels_sync_and_invalidates_source(
    accounts, application, monkeypatch
):
    configure(application)
    monkeypatch.setattr(github_app, "request_json", transport)
    owner, _ = accounts()
    wid = project(owner)
    connection = authorize(owner, wid, application)["connection"]
    factory = application.state.session_factory
    sync_once(factory, settings=application.state.settings)
    with factory() as db:
        job = db.query(RepositorySync).one()
        job.state, job.next_attempt_at = "queued", utc_now()
        db.commit()

    def lost(*args, **kwargs):
        raise SyncError("repository_access_lost")

    monkeypatch.setattr(github_app, "request_json", lost)
    assert sync_once(factory, settings=application.state.settings)
    assert owner.get(f"/workspaces/{wid}/knowledge?kind=external").json()["total"] == 0
    with factory() as db:
        assert db.get(RepositoryConnection, connection["id"]).credential is None
        assert db.query(ImportedRecord).count() == 2  # retained audit rows


def test_device_poll_interval_pending_slowdown_expiry_and_owner_transfer(
    accounts, application, monkeypatch
):
    configure(application)
    monkeypatch.setattr(github_app, "request_json", transport)
    owner, _ = accounts()
    member, profile = accounts("bob@example.test", "Bob")
    wid = project(owner)
    join(owner, member, wid)
    response = owner.post(
        f"/workspaces/{wid}/github-authorizations",
        json={"repository": "org/private", "installation_id": 42},
    )
    aid = response.json()["id"]
    assert (
        owner.get(f"/workspaces/{wid}/github-authorizations").json()["items"][0]["user_code"]
        == "ABCD-EFGH"
    )
    path = f"/workspaces/{wid}/github-authorizations/{aid}/complete"
    assert owner.post(path).status_code == 429
    assert member.post(path).status_code == 403
    with application.state.session_factory() as db:
        row = db.get(GitHubAuthorization, aid)
        row.next_poll_at = utc_now() - timedelta(seconds=1)
        db.commit()
    monkeypatch.setattr(github_app, "request_json", lambda *a, **k: {"error": "slow_down"})
    value = owner.post(path).json()
    assert value["state"] == "pending" and value["interval"] == 10
    with application.state.session_factory() as db:
        row = db.get(GitHubAuthorization, aid)
        row.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert owner.post(path).json()["state"] == "expired"
    monkeypatch.setattr(github_app, "request_json", transport)
    authorize(owner, wid, application)
    assert (
        owner.post(
            f"/workspaces/{wid}/transfer-ownership", json={"user_id": profile["id"]}
        ).status_code
        == 200
    )
    assert member.get(f"/workspaces/{wid}/connections").json()["items"][0]["active"] is False
    assert owner.post(f"/workspaces/{wid}/github-authorizations/{aid}/complete").status_code == 403


def test_private_pagination_and_tampered_credentials_fail_safely(application):
    from types import SimpleNamespace

    configure(application)
    settings = application.state.settings
    row = SimpleNamespace(
        credential=github_app.seal(
            settings,
            {"access_token": "fixture-access-only", "refresh_token": "fixture-refresh-only"},
        ),
        credential_expires_at=utc_now() + timedelta(hours=1),
        installation_id=42,
        repository_id=99,
        repository="org/private",
    )
    paths = []

    def read(path, **kwargs):
        paths.append(path)
        if "/issues?" in path:
            page = int(path.rsplit("page=", 1)[1])
            if page == 1:
                return [{"number": i + 1, "title": "Issue", "state": "open"} for i in range(25)]
            return [{"number": 26, "title": "Next page", "state": "open"}]
        return transport(path, **kwargs)

    records, _, _ = github_app.private_fetch(settings, row, read)
    assert len(records) == 27 and any("page=2" in p for p in paths)
    row.credential = (
        row.credential[:50] + ("A" if row.credential[50] != "A" else "B") + row.credential[51:]
    )
    with pytest.raises(SyncError):
        github_app.private_fetch(settings, row, read)
