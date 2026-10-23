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


def test_shared_abuse_limit_across_instances_and_atomic_competition(application):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi import HTTPException

    from models import AbuseCounter
    from rate_limit import SharedRateLimiter

    a = SharedRateLimiter(
        application.state.session_factory, "test-only-shared-key", limit=3, clock=lambda: 120
    )
    b = SharedRateLimiter(
        application.state.session_factory, "test-only-shared-key", limit=3, clock=lambda: 120
    )

    def check(n):
        try:
            (a if n % 2 else b).check("private-client-address")
            return True
        except HTTPException as exc:
            assert exc.status_code == 429
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(check, range(8))) == 3
    with application.state.session_factory() as db:
        row = db.query(AbuseCounter).one()
        assert row.count == 8 and "private-client" not in row.key
    c = SharedRateLimiter(
        application.state.session_factory, "test-only-shared-key", clock=lambda: 180
    )
    c.check("private-client-address")


def test_restoration_drill_preserves_live_source_and_runs_migrations(tmp_path):
    from restore import restore_sqlite

    original = tmp_path / "existing.db"
    backup = tmp_path / "safe-backup.db"
    destination = tmp_path / "recovery.db"
    upgrade_database(f"sqlite:///{original}", "0009_worker_health")
    before = original.read_bytes()
    backup_sqlite(f"sqlite:///{original}", backup)
    assert restore_sqlite(backup, destination) == destination
    assert original.read_bytes() == before
    engine = create_db_engine(f"sqlite:///{destination}")
    with engine.connect() as db:
        assert (
            db.execute(text("SELECT version_num FROM alembic_version")).scalar()
            == "0013_shared_limits"
        )
    engine.dispose()
    with pytest.raises(FileExistsError):
        restore_sqlite(backup, destination)
