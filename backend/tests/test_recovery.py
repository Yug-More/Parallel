"""Local delivery is a fixture, not proof of email ownership or real mail delivery."""

import json
import stat
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256

from fastapi.testclient import TestClient

from models import RecoveryRequest, utc_now
from recovery import LocalOutbox, deliver_once


def enable(application, tmp_path):
    path = tmp_path / "private-outbox"
    application.state.settings = replace(application.state.settings, recovery_outbox_path=str(path))
    return path


def request_and_deliver(client, application, path, purpose="reset"):
    url = "/auth/recovery/request" if purpose == "reset" else "/auth/verification/request"
    result = client.post(url, json={"email": "alice@example.test"} if purpose == "reset" else None)
    assert result.status_code == 202, result.text
    assert "token" not in result.text
    assert deliver_once(application.state.session_factory, LocalOutbox(path))
    return json.loads(max(path.glob("*.json"), key=lambda p: p.stat().st_mtime_ns).read_text())[
        "token"
    ]


def test_recovery_is_private_one_use_and_revokes_every_session(accounts, application, tmp_path):
    client, _ = accounts()
    path = enable(application, tmp_path)
    second = TestClient(application)
    second.post("/auth/login", json={"email": "alice@example.test", "password": "correct-password"})
    token = request_and_deliver(client, application, path)
    with application.state.session_factory() as db:
        row = db.query(RecoveryRequest).one()
        assert row.token_hash == sha256(token.encode()).hexdigest() and token not in repr(
            row.__dict__
        )
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in path.iterdir())
    payload = {"token": token, "password": "replacement-password"}
    assert client.post("/auth/recovery/complete", json=payload).status_code == 200
    assert second.get("/me").status_code == 401
    assert client.get("/me").status_code == 401
    assert client.post("/auth/recovery/complete", json=payload).status_code == 400
    assert (
        client.post(
            "/auth/login", json={"email": "alice@example.test", "password": "correct-password"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={"email": "alice@example.test", "password": "replacement-password"}
        ).status_code
        == 200
    )


def test_known_unknown_disabled_and_no_delivery_enumeration(accounts, application, tmp_path):
    client, _ = accounts()
    known = client.post("/auth/recovery/request", json={"email": "alice@example.test"})
    unknown = client.post("/auth/recovery/request", json={"email": "unknown@example.test"})
    assert known.status_code == unknown.status_code == 202 and known.json() == unknown.json()
    with application.state.session_factory() as db:
        assert db.query(RecoveryRequest).count() == 0
    path = enable(application, tmp_path)
    known = client.post("/auth/recovery/request", json={"email": "alice@example.test"})
    unknown = client.post("/auth/recovery/request", json={"email": "unknown@example.test"})
    assert known.json() == unknown.json()
    assert not path.exists()
    assert deliver_once(application.state.session_factory, LocalOutbox(path))
    assert deliver_once(application.state.session_factory, LocalOutbox(path))
    assert len(list(path.iterdir())) == 1


def test_expiry_wrong_purpose_new_request_supersedes_and_verification(
    accounts, application, tmp_path
):
    client, _ = accounts()
    path = enable(application, tmp_path)
    old = request_and_deliver(client, application, path)
    new = request_and_deliver(client, application, path)
    assert (
        client.post(
            "/auth/recovery/complete", json={"token": old, "password": "new-password"}
        ).status_code
        == 400
    )
    assert client.post("/auth/verification/complete", json={"token": new}).status_code == 400
    with application.state.session_factory() as db:
        db.query(RecoveryRequest).filter_by(
            token_hash=sha256(new.encode()).hexdigest()
        ).one().expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert (
        client.post(
            "/auth/recovery/complete", json={"token": new, "password": "new-password"}
        ).status_code
        == 400
    )
    verification = request_and_deliver(client, application, path, "verify")
    assert not client.get("/me").json()["email_verified"]
    assert (
        client.post("/auth/verification/complete", json={"token": verification}).status_code == 200
    )
    assert client.get("/me").json()["email_verified"]
    assert (
        client.post("/auth/verification/complete", json={"token": verification}).status_code == 400
    )


def test_outbox_refuses_public_permissions_and_sanitizes_failure(accounts, application, tmp_path):
    client, _ = accounts()
    path = enable(application, tmp_path)
    path.mkdir(mode=0o755)
    client.post("/auth/recovery/request", json={"email": "alice@example.test"})
    assert deliver_once(application.state.session_factory, LocalOutbox(path))
    with application.state.session_factory() as db:
        row = db.query(RecoveryRequest).one()
        assert row.state == "failed" and row.token_hash is None
    assert not list(path.iterdir())


def test_password_byte_limit_and_hmac_address_budget(accounts, application, tmp_path):
    client, _ = accounts()
    path = enable(application, tmp_path)
    token = request_and_deliver(client, application, path)
    assert (
        client.post(
            "/auth/recovery/complete", json={"token": token, "password": "é" * 40}
        ).status_code
        == 422
    )
    for _ in range(2):
        assert (
            client.post("/auth/recovery/request", json={"email": "alice@example.test"}).status_code
            == 202
        )
    assert (
        client.post("/auth/recovery/request", json={"email": "alice@example.test"}).status_code
        == 429
    )


def test_competing_token_consumption_succeeds_once(accounts, application, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    client, _ = accounts()
    path = enable(application, tmp_path)
    token = request_and_deliver(client, application, path)

    def reset(_):
        with TestClient(application) as caller:
            return caller.post(
                "/auth/recovery/complete", json={"token": token, "password": "new-test-password"}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reset, range(2))) == [200, 400]


def test_login_serializes_before_reset_and_new_session_is_revoked(
    accounts, application, tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    import api.auth

    client, _ = accounts()
    path = enable(application, tmp_path)
    token = request_and_deliver(client, application, path)
    entered, release = Event(), Event()
    verify = api.auth.verify_password

    def paused(password, digest):
        entered.set()
        assert release.wait(5)
        return verify(password, digest)

    monkeypatch.setattr(api.auth, "verify_password", paused)
    login_client = TestClient(application)
    with ThreadPoolExecutor(max_workers=2) as pool:
        login = pool.submit(
            login_client.post,
            "/auth/login",
            json={"email": "alice@example.test", "password": "correct-password"},
        )
        assert entered.wait(5)
        reset = pool.submit(
            client.post,
            "/auth/recovery/complete",
            json={"token": token, "password": "replacement-password"},
        )
        release.set()
        assert login.result().status_code == 200
        assert reset.result().status_code == 200
    assert login_client.get("/me").status_code == 401
