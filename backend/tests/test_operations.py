from datetime import timedelta

import pytest
from sqlalchemy import text

from backup import backup_sqlite
from database import create_db_engine
from migrate import upgrade_database
from models import WorkerHeartbeat, utc_now
from worker_health import heartbeat, status


def test_backup_restore_and_overwrite_protection(tmp_path):
    original = tmp_path / "original.db"
    output = tmp_path / "backup.db"
    url = f"sqlite:///{original}"
    upgrade_database(url)
    engine = create_db_engine(url)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO users (id,email,name) VALUES ('user','user@example.test','Preserved')"
            )
        )
    assert backup_sqlite(url, output) == output
    with pytest.raises(FileExistsError):
        backup_sqlite(url, output)
    restored = create_db_engine(f"sqlite:///{output}")
    with restored.connect() as db:
        assert db.execute(text("SELECT name FROM users")).scalar() == "Preserved"
        assert db.execute(text("PRAGMA integrity_check")).scalar() == "ok"
    restored.dispose()
    engine.dispose()


def test_worker_heartbeat_is_recent_polling_not_success(application):
    factory = application.state.session_factory
    heartbeat(factory, "test-worker")
    with factory() as db:
        assert status(db)["active_workers"] == 1
        item = db.get(WorkerHeartbeat, "test-worker")
        item.last_seen_at = utc_now() - timedelta(minutes=2)
        db.commit()
    with factory() as db:
        assert status(db)["active_workers"] == 0
    heartbeat(factory, "test-worker", "stopped")
    with factory() as db:
        assert status(db)["status"] == "not_recently_seen"


def test_readiness_request_ids_and_safe_http_errors(client, application, monkeypatch):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.headers["Cache-Control"] == "no-store"
    client.post(
        "/auth/register",
        json={"name": "Owner", "email": "owner@example.test", "password": "test-long-password"},
    )

    def broken(*_args):
        raise RuntimeError("private exception body")

    monkeypatch.setattr("api.workspaces.create_workspace", broken)
    response = client.post("/workspaces", json={"name": "Safe failure"})
    assert response.status_code == 500
    assert "private exception" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
