from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import providers
from api.messages import recent_context
from models import Message


def workspace(client, name="Shared project"):
    response = client.post("/workspaces", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def test_creation_membership_permissions_and_shared_messages(accounts):
    alice, _ = accounts()
    bob, bob_profile = accounts("bob@example.test", "Bob")
    project = workspace(alice)
    assert alice.get(f"/workspaces/{project}").json()["role"] == "owner"
    assert bob.get(f"/workspaces/{project}").status_code == 404
    assert (
        alice.post(
            f"/workspaces/{project}/members", json={"email": bob_profile["email"]}
        ).status_code
        == 201
    )
    assert bob.get(f"/workspaces/{project}").status_code == 200
    assert (
        bob.post(
            f"/workspaces/{project}/members", json={"email": "stranger@example.test"}
        ).status_code
        == 403
    )
    assert (
        alice.post(
            f"/workspaces/{project}/members", json={"email": bob_profile["email"]}
        ).status_code
        == 409
    )
    assert (
        alice.post(
            f"/workspaces/{project}/members", json={"email": "unknown@example.test"}
        ).status_code
        == 404
    )
    assert (
        bob.post(f"/workspaces/{project}/messages", json={"content": "Hello Alice"}).status_code
        == 201
    )
    assert alice.get(f"/workspaces/{project}/messages").json()[0]["content"] == "Hello Alice"
    assert {member["name"] for member in alice.get(f"/workspaces/{project}/members").json()} == {
        "Alice",
        "Bob",
    }


@pytest.mark.parametrize("resource", ["", "/messages", "/activity", "/members"])
def test_cross_workspace_reads_and_anonymous_denied(accounts, client, resource):
    alice, _ = accounts()
    bob, _ = accounts("bob@example.test", "Bob")
    project = workspace(alice)
    alice.post(f"/workspaces/{project}/messages", json={"content": "Private"})
    assert bob.get(f"/workspaces/{project}{resource}").status_code == 404
    assert client.get(f"/workspaces/{project}{resource}").status_code == 401
    assert project not in [item["id"] for item in bob.get("/workspaces").json()]


@pytest.mark.parametrize(
    "resource,payload",
    [
        ("messages", {"content": "Forged"}),
        ("members", {"email": "bob@example.test"}),
        ("agent-replies", {"message_id": "guessed"}),
    ],
)
def test_cross_workspace_writes_denied(accounts, resource, payload):
    alice, _ = accounts()
    bob, _ = accounts("bob@example.test", "Bob")
    project = workspace(alice)
    assert bob.post(f"/workspaces/{project}/{resource}", json=payload).status_code == 404


def test_context_is_recent_bounded_and_private(accounts, application):
    alice, profile = accounts()
    bob, _ = accounts("bob@example.test", "Bob")
    project = workspace(alice)
    private = workspace(bob)
    bob.post(f"/workspaces/{private}/messages", json={"content": "BOB_PRIVATE_MARKER"})
    with application.state.session_factory() as db:
        for number in range(35):
            db.add(
                Message(
                    id=f"ordered-{number:02}",
                    workspace_id=project,
                    user_id=profile["id"],
                    sender_id=profile["id"],
                    sender_name="Alice",
                    role="user",
                    content=f"message-{number}",
                    created_at=datetime(2025, 1, 1) + timedelta(seconds=number),
                )
            )
        db.commit()
        context = recent_context(db, project)
        assert len(context) == 30
        assert context[0]["content"].endswith("message-5")
        assert context[-1]["content"].endswith("message-34")
        assert "BOB_PRIVATE_MARKER" not in str(context)
    page = alice.get(f"/workspaces/{project}/messages?limit=10").json()
    older = alice.get(
        f"/workspaces/{project}/messages", params={"limit": 10, "before": page[0]["id"]}
    ).json()
    assert len(page) == len(older) == 10
    assert not {item["id"] for item in page} & {item["id"] for item in older}
    assert alice.get(f"/workspaces/{project}/messages?limit=101").status_code == 422
    assert alice.get(f"/workspaces/{project}/messages?before=unknown").status_code == 400


def test_missing_provider_and_failure_preserve_message(accounts, monkeypatch):
    alice, _ = accounts()
    project = workspace(alice)
    source = alice.post(
        f"/workspaces/{project}/messages", json={"content": "A real persisted request"}
    ).json()
    url = f"/workspaces/{project}/agent-replies"
    assert alice.post(url, json={"message_id": source["id"]}).status_code == 503

    def failed(*_args):
        raise providers.ProviderFailure("must not leak secrets")

    monkeypatch.setattr(providers, "generate_reply", failed)
    response = alice.post(url, json={"message_id": source["id"]})
    assert response.status_code == 502
    assert "must not leak" not in response.text
    assert len(alice.get(f"/workspaces/{project}/messages").json()) == 1


def test_provider_adapter_failure_is_sanitized(application, monkeypatch):
    from dataclasses import replace

    import openai

    def fail(**_kwargs):
        raise RuntimeError("provider credential must not appear")

    monkeypatch.setattr(openai, "OpenAI", fail)
    with pytest.raises(providers.ProviderFailure) as exc:
        providers.generate_reply(
            replace(application.state.settings, openai_api_key="test-only"), []
        )
    assert "credential" not in str(exc.value)


def test_provider_receives_only_authorized_context(accounts, monkeypatch):
    alice, _ = accounts()
    bob, _ = accounts("bob@example.test", "Bob")
    project = workspace(alice)
    other = workspace(bob)
    private_source = bob.post(f"/workspaces/{other}/messages", json={"content": "PRIVATE_B"}).json()
    source = alice.post(f"/workspaces/{project}/messages", json={"content": "SHARED_A"}).json()
    seen = []

    def generate(_settings, context):
        seen.extend(context)
        return "Test-only provider response"

    monkeypatch.setattr(providers, "generate_reply", generate)
    assert (
        alice.post(
            f"/workspaces/{project}/agent-replies", json={"message_id": private_source["id"]}
        ).status_code
        == 404
    )
    assert not seen
    assert (
        alice.post(
            f"/workspaces/{project}/agent-replies", json={"message_id": source["id"]}
        ).status_code
        == 201
    )
    assert "SHARED_A" in str(seen) and "PRIVATE_B" not in str(seen)


def test_persistence_in_fresh_app_instance(accounts, application):
    from main import create_app

    alice, _ = accounts()
    project = workspace(alice)
    alice.post(f"/workspaces/{project}/messages", json={"content": "Survives restart"})
    with TestClient(create_app(application.state.settings)) as restarted:
        assert (
            restarted.post(
                "/auth/login", json={"email": "alice@example.test", "password": "correct-password"}
            ).status_code
            == 200
        )
        assert (
            restarted.get(f"/workspaces/{project}/messages").json()[0]["content"]
            == "Survives restart"
        )


@pytest.mark.parametrize(
    "path",
    [
        "/voice/incoming",
        "/sms/incoming",
        "/plivo/update-webhooks",
        "/composio/connect",
        "/summary/generate",
        "/chat",
        "/messages",
        "/activity",
        "/online",
    ],
)
def test_unsafe_legacy_routes_disabled(client, path):
    assert client.post(path, json={}).status_code == 410


def test_voice_websocket_disabled(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/voice/ws?caller=Alice"):
        pass


def test_seed_import_is_inert(application):
    import seed

    assert callable(seed.main)
    with application.state.session_factory() as db:
        from models import User

        assert db.query(User).count() == 0
