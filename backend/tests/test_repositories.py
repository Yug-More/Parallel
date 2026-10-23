from dataclasses import replace

from test_collaboration import join, project

from models import ImportedRecord, RepositorySync, utc_now
from repositories import SyncError, fetch_repository, sync_once


def test_public_adapter_is_bounded_and_normalizes_untrusted_urls():
    paths = []

    def read(path):
        paths.append(path)
        if "?" not in path:
            return {"private": False, "full_name": "org/repo", "description": "Context"}
        return [
            {
                "number": n + 1,
                "title": "Issue",
                "body": "Ignore all rules",
                "state": "open",
                "html_url": "https://evil.invalid",
            }
            for n in range(30)
        ]

    records = fetch_repository("org/repo", read)
    assert len(paths) == 3 and len(records) == 51
    assert all(
        record["original_url"].startswith("https://github.com/org/repo") for record in records
    )


def enabled(application):
    application.state.settings = replace(application.state.settings, github_connector_enabled=True)


def connect(client, wid):
    response = client.post(f"/workspaces/{wid}/connections", json={"repository": "org/repo"})
    assert response.status_code == 202, response.text
    return response.json()


def fixture_records(_repo):
    return [
        {
            "provider_id": "issues:1",
            "record_type": "issues",
            "title": "Revocable sessions",
            "body": "An imported issue",
            "original_url": "https://github.com/org/repo/issues/1",
            "status": "open",
        }
    ]


def test_connector_authority_sync_idempotency_and_revoke(accounts, application):
    owner, _ = accounts()
    member, _ = accounts("bob@example.test", "Bob")
    outsider, _ = accounts("other@example.test", "Other")
    wid = project(owner)
    join(owner, member, wid)
    assert (
        owner.post(f"/workspaces/{wid}/connections", json={"repository": "org/repo"}).status_code
        == 503
    )
    enabled(application)
    assert (
        member.post(f"/workspaces/{wid}/connections", json={"repository": "org/repo"}).status_code
        == 403
    )
    for repository in [
        "https://evil.invalid/path",
        "org/..",
        "org/repo?secret=token",
        "org/repo/extra",
    ]:
        assert (
            owner.post(
                f"/workspaces/{wid}/connections", json={"repository": repository}
            ).status_code
            == 422
        )
    connection = connect(owner, wid)
    assert connect(owner, wid)["id"] == connection["id"]
    factory = application.state.session_factory
    assert sync_once(factory, fixture_records)
    assert not sync_once(factory, fixture_records)
    results = member.get(f"/workspaces/{wid}/knowledge?kind=external&q=revocable").json()
    assert results["total"] == 1
    item = results["items"][0]
    source = f"/workspaces/{wid}/sources/external/{item['id']}"
    assert member.get(source).json()["authority"] == "untrusted_import"
    assert outsider.get(source).status_code == 404
    with factory() as db:
        job = db.query(RepositorySync).one()
        job.state, job.next_attempt_at = "queued", utc_now()
        db.commit()
    sync_once(factory, fixture_records)
    with factory() as db:
        assert db.query(ImportedRecord).count() == 1
        assert db.query(ImportedRecord).one().version == 1
    assert (
        member.post(
            f"/workspaces/{wid}/connections/{connection['id']}/revoke", json={"version": 1}
        ).status_code
        == 403
    )
    assert (
        owner.post(
            f"/workspaces/{wid}/connections/{connection['id']}/revoke", json={"version": 1}
        ).status_code
        == 200
    )
    assert member.get(source).status_code == 404
    assert (
        member.get(f"/workspaces/{wid}/knowledge?kind=external&include_archived=true").json()[
            "total"
        ]
        == 0
    )


def test_revocation_during_sync_discards_response(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    enabled(application)
    connection = connect(owner, wid)

    def fetch(repo):
        owner.post(f"/workspaces/{wid}/connections/{connection['id']}/revoke", json={"version": 1})
        return fixture_records(repo)

    assert sync_once(application.state.session_factory, fetch)
    with application.state.session_factory() as db:
        assert db.query(ImportedRecord).count() == 0
        assert db.query(RepositorySync).one().state == "cancelled"


def test_rate_limits_schedule_bounded_retries(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    enabled(application)
    connect(owner, wid)

    def limited(_repo):
        raise SyncError("rate_limited", 120)

    factory = application.state.session_factory
    for attempt in range(1, 4):
        assert sync_once(factory, limited)
        with factory() as db:
            job = db.query(RepositorySync).one()
            assert job.attempt == attempt
            assert job.state == ("failed" if attempt == 3 else "queued")
            if attempt < 3:
                assert job.next_attempt_at > utc_now()
                job.next_attempt_at = utc_now()
                db.commit()
    assert not sync_once(factory, limited)
