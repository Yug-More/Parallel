from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.messages import recent_context
from main import create_app
from models import AuthSession, Invitation, Membership, Task, utc_now
from rate_limit import AuthRateLimiter


def project(client):
    return client.post("/workspaces", json={"name": "Collaboration"}).json()["id"]


def invite(owner, workspace_id, email="bob@example.test"):
    response = owner.post(f"/workspaces/{workspace_id}/invitations", json={"email": email})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def join(owner, member, workspace_id, email="bob@example.test"):
    invitation = invite(owner, workspace_id, email)
    assert member.post(f"/invitations/{invitation}/accept").status_code == 200
    return invitation


def task(client, workspace_id, **changes):
    response = client.post(
        f"/workspaces/{workspace_id}/tasks", json={"title": "Persistent task", **changes}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_invitation_acceptance_identity_and_replay(accounts):
    alice, _ = accounts()
    bob, _ = accounts("bob@example.test", "Bob")
    outsider, _ = accounts("other@example.test", "Other")
    wid = project(alice)
    iid = invite(alice, wid)
    assert bob.get(f"/workspaces/{wid}").status_code == 404
    assert len(bob.get("/invitations").json()) == 1
    assert outsider.post(f"/invitations/{iid}/accept").status_code == 404
    assert outsider.get(f"/workspaces/{wid}/invitations").status_code == 404
    assert bob.post(f"/invitations/{iid}/accept").status_code == 200
    assert bob.get(f"/workspaces/{wid}").json()["role"] == "member"
    assert bob.post(f"/invitations/{iid}/accept").status_code == 409
    assert bob.get("/invitations").json() == []
    assert len(alice.get(f"/workspaces/{wid}/members").json()) == 2


@pytest.mark.parametrize("action", ["decline", "revoke", "expire"])
def test_terminal_invitations_cannot_be_reused(accounts, application, action):
    alice, _ = accounts()
    bob, _ = accounts("bob@example.test", "Bob")
    wid = project(alice)
    iid = invite(alice, wid)
    if action == "decline":
        assert bob.post(f"/invitations/{iid}/decline").status_code == 200
    elif action == "revoke":
        assert alice.post(f"/workspaces/{wid}/invitations/{iid}/revoke").status_code == 200
    else:
        with application.state.session_factory() as db:
            db.get(Invitation, iid).expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
    response = bob.post(f"/invitations/{iid}/accept")
    assert response.status_code == (410 if action == "expire" else 409)
    assert bob.get(f"/workspaces/{wid}").status_code == 404
    replacement = invite(alice, wid)
    assert replacement != iid
    assert bob.post(f"/invitations/{iid}/accept").status_code == 409
    assert bob.post(f"/invitations/{replacement}/accept").status_code == 200


def test_duplicate_and_unauthorized_invites(accounts):
    alice, _ = accounts()
    bob, _ = accounts("bob@example.test", "Bob")
    wid = project(alice)
    invite(alice, wid)
    assert (
        alice.post(f"/workspaces/{wid}/invitations", json={"email": "bob@example.test"}).status_code
        == 409
    )
    assert (
        alice.post(
            f"/workspaces/{wid}/invitations", json={"email": "absent@example.test"}
        ).status_code
        == 404
    )
    assert (
        alice.post(
            f"/workspaces/{wid}/invitations", json={"email": "alice@example.test"}
        ).status_code
        == 409
    )
    assert (
        alice.post(
            f"/workspaces/{wid}/invitations",
            json={"email": "bob@example.test", "expires_in_days": 31},
        ).status_code
        == 422
    )
    join_id = bob.get("/invitations").json()[0]["id"]
    bob.post(f"/invitations/{join_id}/accept")
    assert (
        bob.post(f"/workspaces/{wid}/invitations", json={"email": "alice@example.test"}).status_code
        == 403
    )
    assert bob.get(f"/workspaces/{wid}/invitations").status_code == 403
    assert bob.patch(f"/workspaces/{wid}/members", json={"role": "owner"}).status_code != 200


def test_removal_revokes_all_resources_and_unassigns_tasks(accounts, application):
    alice, _ = accounts()
    bob, bob_user = accounts("bob@example.test", "Bob")
    wid = project(alice)
    join(alice, bob, wid)
    created = task(alice, wid, assignee_id=bob_user["id"])
    source = bob.post(
        f"/workspaces/{wid}/messages", json={"content": "Persisted before removal"}
    ).json()
    assert alice.delete(f"/workspaces/{wid}/members/{bob_user['id']}").status_code == 200
    for suffix in ["", "/members", "/messages", "/tasks", "/activity", f"/tasks/{created['id']}"]:
        assert bob.get(f"/workspaces/{wid}{suffix}").status_code == 404
    assert bob.post(f"/workspaces/{wid}/messages", json={"content": "forged"}).status_code == 404
    assert (
        bob.post(f"/workspaces/{wid}/agent-replies", json={"message_id": source["id"]}).status_code
        == 404
    )
    updated = alice.get(f"/workspaces/{wid}/tasks/{created['id']}").json()
    assert updated["assignee_id"] is None and updated["version"] == 2
    assert (
        alice.patch(
            f"/workspaces/{wid}/tasks/{created['id']}",
            json={"version": 2, "assignee_id": bob_user["id"]},
        ).status_code
        == 422
    )
    with application.state.session_factory() as db:
        assert "Persisted before removal" in str(recent_context(db, wid))


def test_ownership_transfer_leave_and_pending_revocation(accounts, application):
    alice, alice_user = accounts()
    bob, bob_user = accounts("bob@example.test", "Bob")
    accounts("other@example.test", "Other")
    wid = project(alice)
    assert alice.post(f"/workspaces/{wid}/leave").status_code == 409
    assert alice.delete(f"/workspaces/{wid}/members/{alice_user['id']}").status_code == 409
    assert (
        alice.post(
            f"/workspaces/{wid}/transfer-ownership", json={"user_id": bob_user["id"]}
        ).status_code
        == 422
    )
    join(alice, bob, wid)
    iid = invite(alice, wid, "other@example.test")
    assert (
        bob.post(
            f"/workspaces/{wid}/transfer-ownership", json={"user_id": alice_user["id"]}
        ).status_code
        == 403
    )
    assert (
        alice.post(
            f"/workspaces/{wid}/transfer-ownership", json={"user_id": alice_user["id"]}
        ).status_code
        == 409
    )
    assert (
        alice.post(
            f"/workspaces/{wid}/transfer-ownership", json={"user_id": bob_user["id"]}
        ).status_code
        == 200
    )
    assert bob.get(f"/workspaces/{wid}").json()["role"] == "owner"
    assert alice.get(f"/workspaces/{wid}").json()["role"] == "member"
    assert (
        alice.post(
            f"/workspaces/{wid}/invitations", json={"email": "other@example.test"}
        ).status_code
        == 403
    )
    with application.state.session_factory() as db:
        assert db.get(Invitation, iid).status == "revoked"
        assert db.query(Membership).filter_by(workspace_id=wid, role="owner").count() == 1
    assert alice.post(f"/workspaces/{wid}/leave").status_code == 200
    assert alice.get(f"/workspaces/{wid}").status_code == 404
    assert bob.post(f"/workspaces/{wid}/leave").status_code == 409


def test_task_lifecycle_assignment_and_restart(accounts, application):
    alice, _ = accounts()
    bob, bob_user = accounts("bob@example.test", "Bob")
    wid = project(alice)
    join(alice, bob, wid)
    item = task(
        alice,
        wid,
        description="Real details",
        priority="high",
        due_date="2026-12-01",
        assignee_id=bob_user["id"],
    )
    response = bob.patch(
        f"/workspaces/{wid}/tasks/{item['id']}",
        json={
            "version": item["version"],
            "status": "in_progress",
            "description": "Updated details",
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["version"] == 2 and updated["creator_name"] == "Alice"
    assert updated["assignee_name"] == "Bob" and updated["due_date"] == "2026-12-01"
    assert (
        alice.patch(
            f"/workspaces/{wid}/tasks/{item['id']}", json={"version": 1, "status": "done"}
        ).status_code
        == 409
    )
    with TestClient(create_app(application.state.settings)) as restarted:
        restarted.cookies.update(bob.cookies)
        assert (
            restarted.get(f"/workspaces/{wid}/tasks/{item['id']}").json()["description"]
            == "Updated details"
        )
    assert (
        alice.post(f"/workspaces/{wid}/tasks/{item['id']}/archive", json={"version": 2}).status_code
        == 200
    )
    assert alice.get(f"/workspaces/{wid}/tasks").json()["total"] == 0
    assert alice.get(f"/workspaces/{wid}/tasks?archived=true").json()["items"][0]["archived"]
    assert (
        bob.patch(
            f"/workspaces/{wid}/tasks/{item['id']}", json={"version": 3, "title": "Lost data"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ""},
        {"status": "unknown"},
        {"priority": "unknown"},
        {"due_date": "yesterday"},
        {"creator_id": "forged"},
        {"description": "x" * 12001},
    ],
)
def test_task_input_validation(accounts, changes):
    alice, _ = accounts()
    wid = project(alice)
    assert (
        alice.post(f"/workspaces/{wid}/tasks", json={"title": "Valid", **changes}).status_code
        == 422
    )


def test_tasks_and_dependencies_cannot_cross_workspaces(accounts):
    alice, _ = accounts()
    bob, bob_user = accounts("bob@example.test", "Bob")
    wid = project(alice)
    private = project(bob)
    other = task(bob, private)
    assert (
        alice.post(
            f"/workspaces/{wid}/tasks",
            json={"title": "Bad assignment", "assignee_id": bob_user["id"]},
        ).status_code
        == 422
    )
    assert (
        alice.post(
            f"/workspaces/{wid}/tasks",
            json={"title": "Bad dependency", "dependency_ids": [other["id"]]},
        ).status_code
        == 422
    )
    assert alice.get(f"/workspaces/{wid}/tasks/{other['id']}").status_code == 404
    assert bob.get(f"/workspaces/{wid}/tasks").status_code == 404
    assert bob.post(f"/workspaces/{wid}/tasks", json={"title": "Forged"}).status_code == 404
    assert alice.get(f"/workspaces/{wid}/tasks?limit=101").status_code == 422


def test_dependency_cycles_completion_and_archival(accounts):
    alice, _ = accounts()
    wid = project(alice)
    first = task(alice, wid, title="First")
    second = task(alice, wid, title="Second", dependency_ids=[first["id"]])
    third = task(alice, wid, title="Third", dependency_ids=[second["id"]])
    url = f"/workspaces/{wid}/tasks/{first['id']}"
    assert alice.patch(url, json={"version": 1, "dependency_ids": [first["id"]]}).status_code == 422
    assert alice.patch(url, json={"version": 1, "dependency_ids": [third["id"]]}).status_code == 409
    assert (
        alice.patch(
            f"/workspaces/{wid}/tasks/{second['id']}", json={"version": 1, "status": "done"}
        ).status_code
        == 409
    )
    assert alice.post(url + "/archive", json={"version": 1}).status_code == 409
    assert alice.patch(url, json={"version": 1, "status": "done"}).status_code == 200
    assert (
        alice.patch(
            f"/workspaces/{wid}/tasks/{second['id']}", json={"version": 1, "status": "done"}
        ).status_code
        == 200
    )
    assert alice.patch(url, json={"version": 2, "status": "todo"}).status_code == 409
    assert (
        alice.patch(
            f"/workspaces/{wid}/tasks/{second['id']}", json={"version": 2, "dependency_ids": []}
        ).status_code
        == 200
    )
    assert alice.post(url + "/archive", json={"version": 2}).status_code == 200


def test_task_noop_and_stale_retry_do_not_duplicate_activity(accounts):
    alice, _ = accounts()
    wid = project(alice)
    item = task(alice, wid)
    url = f"/workspaces/{wid}/tasks/{item['id']}"
    assert alice.patch(url, json={"version": 1, "title": item["title"]}).json()["version"] == 1
    assert len(alice.get(f"/workspaces/{wid}/activity").json()) == 1
    assert alice.patch(url, json={"version": 1, "status": "blocked"}).status_code == 200
    assert alice.patch(url, json={"version": 1, "status": "blocked"}).status_code == 409
    assert len(alice.get(f"/workspaces/{wid}/activity").json()) == 2


def test_logout_revokes_copied_token_and_logout_all_other_sessions(accounts, application):
    alice, _ = accounts()
    copy = TestClient(application)
    copy.cookies.update(alice.cookies)
    another = TestClient(application)
    another.post(
        "/auth/login", json={"email": "alice@example.test", "password": "correct-password"}
    )
    assert alice.post("/auth/logout").status_code == 200
    assert copy.get("/me").status_code == 401
    assert another.get("/me").status_code == 200
    independent = TestClient(application)
    independent.post(
        "/auth/login", json={"email": "alice@example.test", "password": "correct-password"}
    )
    other_account, _ = accounts("other@example.test", "Other")
    assert another.post("/auth/logout-all").status_code == 200
    assert independent.get("/me").status_code == 401
    assert other_account.get("/me").status_code == 200
    assert another.get("/me").status_code == 401
    with application.state.session_factory() as db:
        assert db.query(AuthSession).filter(AuthSession.revoked_at.is_(None)).count() == 1


def test_session_expiry_and_auth_throttling(accounts, application):
    alice, _ = accounts()
    with application.state.session_factory() as db:
        session = db.query(AuthSession).one()
        session.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert alice.get("/me").status_code == 401
    now = [100.0]
    application.state.auth_limiter = AuthRateLimiter(limit=2, window=60, clock=lambda: now[0])
    payload = {"email": "absent@example.test", "password": "incorrect"}
    assert alice.post("/auth/login", json=payload).status_code == 401
    assert alice.post("/auth/login", json=payload).status_code == 401
    assert (
        alice.post(
            "/auth/register",
            json={"email": "new@example.test", "name": "New", "password": "correct-password"},
        ).status_code
        == 429
    )
    now[0] += 61
    assert alice.post("/auth/login", json=payload).status_code == 401


def test_concurrent_task_updates_use_one_version(accounts, application):
    alice, _ = accounts()
    wid = project(alice)
    item = task(alice, wid)

    def update(title):
        client = TestClient(application)
        client.cookies.update(alice.cookies)
        return client.patch(
            f"/workspaces/{wid}/tasks/{item['id']}", json={"version": 1, "title": title}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, ["Edit A", "Edit B"]))
    assert sorted(results) == [200, 409]
    assert len(alice.get(f"/workspaces/{wid}/activity").json()) == 2


def test_concurrent_invitation_creation_and_acceptance(accounts, application):
    alice, _ = accounts()
    bob, _ = accounts("bob@example.test", "Bob")
    wid = project(alice)

    def send(_):
        client = TestClient(application)
        client.cookies.update(alice.cookies)
        return client.post(
            f"/workspaces/{wid}/invitations", json={"email": "bob@example.test"}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(send, range(2))) == [201, 409]
    iid = bob.get("/invitations").json()[0]["id"]

    def accept(_):
        client = TestClient(application)
        client.cookies.update(bob.cookies)
        return client.post(f"/invitations/{iid}/accept").status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(accept, range(2))) == [200, 409]
    assert len(alice.get(f"/workspaces/{wid}/members").json()) == 2


def test_database_constraints_enforce_membership_and_single_owner(accounts, application):
    alice, _ = accounts()
    _, outsider = accounts("other@example.test", "Other")
    wid = project(alice)
    item = task(alice, wid)
    with application.state.session_factory() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                text("UPDATE tasks SET assignee_id=:user WHERE id=:task"),
                {"user": outsider["id"], "task": item["id"]},
            )
            db.commit()
        db.rollback()
        with pytest.raises(IntegrityError):
            db.add(Membership(workspace_id=wid, user_id=outsider["id"], role="owner"))
            db.commit()
        db.rollback()
        assert db.query(Task).count() == 1


def test_acceptance_racing_revocation_is_atomic(accounts, application):
    alice, _ = accounts()
    bob, _ = accounts("bob@example.test", "Bob")
    wid = project(alice)
    iid = invite(alice, wid)

    def operation(action):
        client = TestClient(application)
        client.cookies.update(bob.cookies if action == "accept" else alice.cookies)
        url = (
            f"/invitations/{iid}/accept"
            if action == "accept"
            else f"/workspaces/{wid}/invitations/{iid}/revoke"
        )
        return action, client.post(url).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        result = dict(executor.map(operation, ["accept", "revoke"]))
    assert sorted(result.values()) == [200, 409]
    assert (bob.get(f"/workspaces/{wid}").status_code == 200) == (result["accept"] == 200)


def test_removal_racing_assignment_never_leaves_an_invalid_assignee(accounts, application):
    alice, _ = accounts()
    bob, bob_user = accounts("bob@example.test", "Bob")
    wid = project(alice)
    join(alice, bob, wid)
    item = task(alice, wid)

    def operation(action):
        client = TestClient(application)
        client.cookies.update(alice.cookies)
        if action == "remove":
            return action, client.delete(f"/workspaces/{wid}/members/{bob_user['id']}").status_code
        return action, client.patch(
            f"/workspaces/{wid}/tasks/{item['id']}",
            json={"version": 1, "assignee_id": bob_user["id"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        result = dict(executor.map(operation, ["remove", "assign"]))
    assert result["remove"] == 200
    assert result["assign"] in {200, 422}
    assert alice.get(f"/workspaces/{wid}/tasks/{item['id']}").json()["assignee_id"] is None


def test_competing_ownership_transfers_leave_exactly_one_owner(accounts, application):
    alice, _ = accounts()
    bob, bob_user = accounts("bob@example.test", "Bob")
    other, other_user = accounts("other@example.test", "Other")
    wid = project(alice)
    join(alice, bob, wid)
    join(alice, other, wid, "other@example.test")

    def transfer(target):
        client = TestClient(application)
        client.cookies.update(alice.cookies)
        return client.post(
            f"/workspaces/{wid}/transfer-ownership", json={"user_id": target}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(transfer, [bob_user["id"], other_user["id"]]))
    assert sorted(results) == [200, 403]
    with application.state.session_factory() as db:
        from models import Workspace

        owner = db.query(Membership).filter_by(workspace_id=wid, role="owner").one()
        assert db.get(Workspace, wid).owner_id == owner.user_id


def test_membership_removed_during_provider_call_does_not_persist_reply(
    accounts, application, monkeypatch
):
    import providers

    alice, _ = accounts()
    bob, bob_user = accounts("bob@example.test", "Bob")
    wid = project(alice)
    join(alice, bob, wid)
    message = bob.post(f"/workspaces/{wid}/messages", json={"content": "Before removal"}).json()

    def generate(_settings, _context):
        assert alice.delete(f"/workspaces/{wid}/members/{bob_user['id']}").status_code == 200
        return "Must not be persisted after removal"

    monkeypatch.setattr(providers, "generate_reply", generate)
    assert (
        bob.post(f"/workspaces/{wid}/agent-replies", json={"message_id": message["id"]}).status_code
        == 404
    )
    assert len(alice.get(f"/workspaces/{wid}/messages").json()) == 1


def test_member_cannot_remove_owner_or_escalate_roles(accounts):
    alice, alice_user = accounts()
    bob, _ = accounts("bob@example.test", "Bob")
    wid = project(alice)
    invitation = join(alice, bob, wid)
    assert bob.delete(f"/workspaces/{wid}/members/{alice_user['id']}").status_code == 403
    assert bob.post(f"/workspaces/{wid}/invitations/{invitation}/revoke").status_code == 403
    assert (
        alice.post(
            f"/workspaces/{wid}/members", json={"email": "bob@example.test", "role": "owner"}
        ).status_code
        == 422
    )
    assert alice.get(f"/workspaces/{wid}").json()["role"] == "owner"


def test_jwt_expiry_is_rejected_even_with_a_live_session_record(accounts, application):
    import jwt

    alice, _ = accounts()
    key = application.state.settings.secret_key
    payload = jwt.decode(alice.cookies.get("access_token"), key, algorithms=["HS256"])
    payload["exp"] = 1
    alice.cookies.clear()
    alice.cookies.set("access_token", jwt.encode(payload, key, algorithm="HS256"))
    assert alice.get("/me").status_code == 401
