import pytest
from sqlalchemy import inspect, text

from database import create_db_engine
from migrate import upgrade_database
from security import hash_password


def test_legacy_data_preserved_and_privately_backfilled(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    upgrade_database(url, "0001_legacy")
    engine = create_db_engine(url)
    with engine.begin() as db:
        for user in ["alice", "bob"]:
            db.execute(
                text("INSERT INTO users (id,email,name) VALUES (:id,:email,:id)"),
                {"id": user, "email": f"{user}@example.test"},
            )
            db.execute(
                text("INSERT INTO user_credentials (user_id,password_hash) VALUES (:id,:hash)"),
                {"id": user, "hash": hash_password("pass")},
            )
            db.execute(
                text(
                    "INSERT INTO messages (id,user_id,sender_id,sender_name,role,content) VALUES (:id,:id,:id,:id,'user',:content)"
                ),
                {"id": user, "content": f"private-{user}"},
            )
            db.execute(
                text(
                    "INSERT INTO activities (id,user_id,user_name,summary) VALUES (:id,:id,:id,'preserved activity')"
                ),
                {"id": user},
            )
        # Simulate a genuinely unversioned legacy database.
        db.execute(text("DELETE FROM alembic_version"))
    upgrade_database(url)
    upgrade_database(url)  # rerunning must be safe
    with engine.connect() as db:
        assert db.execute(text("SELECT COUNT(*) FROM users")).scalar() == 2
        assert db.execute(text("SELECT COUNT(*) FROM user_credentials")).scalar() == 2
        rows = db.execute(
            text(
                "SELECT m.user_id,m.content,w.owner_id,m.workspace_id FROM messages m JOIN workspaces w ON w.id=m.workspace_id"
            )
        ).all()
        assert len(rows) == 2
        assert all(
            row.user_id == row.owner_id and row.content == f"private-{row.user_id}" for row in rows
        )
        assert rows[0].workspace_id != rows[1].workspace_id
        assert db.execute(text("SELECT COUNT(*) FROM workspace_memberships")).scalar() == 2
        assert (
            db.execute(
                text(
                    "SELECT COUNT(*) FROM activities WHERE summary='preserved activity' AND workspace_id IS NOT NULL"
                )
            ).scalar()
            == 2
        )
    assert not any(
        column["nullable"]
        for column in inspect(engine).get_columns("messages")
        if column["name"] == "workspace_id"
    )
    from fastapi.testclient import TestClient

    from config import Settings
    from main import create_app

    with TestClient(
        create_app(Settings(database_url=url, secret_key="test-only-legacy-session-signing-key"))
    ) as client:
        assert (
            client.post(
                "/auth/login", json={"email": "alice@example.test", "password": "pass"}
            ).status_code
            == 200
        )
        workspaces = client.get("/workspaces").json()
        assert len(workspaces) == 1
        assert (
            client.get(f"/workspaces/{workspaces[0]['id']}/messages").json()[0]["content"]
            == "private-alice"
        )
    engine.dispose()


def test_orphan_ownership_stops_migration_without_deleting_records(tmp_path):
    url = f"sqlite:///{tmp_path / 'orphan.db'}"
    upgrade_database(url, "0001_legacy")
    engine = create_db_engine(url)
    with engine.connect() as db:
        db.exec_driver_sql("PRAGMA foreign_keys=OFF")
        db.execute(
            text(
                "INSERT INTO messages (id,user_id,sender_id,sender_name,role,content) VALUES ('orphan','missing','missing','Missing','user','preserve me')"
            )
        )
        db.commit()
    with pytest.raises(RuntimeError, match="Orphan ownership"):
        upgrade_database(url)
    with engine.connect() as db:
        assert (
            db.execute(text("SELECT content FROM messages WHERE id='orphan'")).scalar()
            == "preserve me"
        )
    engine.dispose()


def test_unknown_legacy_schema_is_rejected(tmp_path):
    url = f"sqlite:///{tmp_path / 'unknown.db'}"
    engine = create_db_engine(url)
    with engine.begin() as db:
        db.execute(text("CREATE TABLE users (id TEXT PRIMARY KEY, private_note TEXT)"))
        db.execute(text("INSERT INTO users VALUES ('keep', 'do not discard')"))
    with pytest.raises(RuntimeError, match="Unsupported legacy schema"):
        upgrade_database(url)
    with engine.connect() as db:
        assert db.execute(text("SELECT private_note FROM users")).scalar() == "do not discard"
    engine.dispose()


def test_phase1a_upgrade_preserves_records_and_requires_new_login(tmp_path):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from config import Settings
    from main import create_app
    from models import Membership, Workspace

    url = f"sqlite:///{tmp_path / 'phase1a.db'}"
    upgrade_database(url, "0002_workspaces")
    engine = create_db_engine(url)
    with engine.begin() as db:
        db.execute(
            text("INSERT INTO users (id,email,name) VALUES ('owner','owner@example.test','Owner')")
        )
        db.execute(
            text("INSERT INTO user_credentials (user_id,password_hash) VALUES ('owner',:hash)"),
            {"hash": hash_password("correct-password")},
        )
        db.execute(
            text(
                "INSERT INTO workspaces (id,name,owner_id,created_at) VALUES ('workspace','Preserved','owner','2026-01-01')"
            )
        )
        db.execute(
            text(
                "INSERT INTO workspace_memberships (workspace_id,user_id,role,created_at) VALUES ('workspace','owner','owner','2026-01-01')"
            )
        )
        db.execute(
            text(
                "INSERT INTO messages (id,user_id,workspace_id,sender_id,sender_name,role,content,created_at) VALUES ('message','owner','workspace','owner','Owner','user','Keep this','2026-01-01')"
            )
        )
        db.execute(
            text(
                "INSERT INTO activities (id,user_id,workspace_id,user_name,summary) VALUES ('activity','owner','workspace','Owner','Keep activity')"
            )
        )
    upgrade_database(url)
    upgrade_database(url)
    with Session(engine) as db:
        assert db.get(Workspace, "workspace").name == "Preserved"
        assert (
            db.execute(text("SELECT summary FROM activities WHERE id='activity'")).scalar()
            == "Keep activity"
        )
        assert db.get(Membership, ("workspace", "owner")).role == "owner"
    with TestClient(
        create_app(Settings(database_url=url, secret_key="test-only-migration-session-signing-key"))
    ) as client:
        assert (
            client.post(
                "/auth/login", json={"email": "owner@example.test", "password": "correct-password"}
            ).status_code
            == 200
        )
        assert client.get("/workspaces/workspace/messages").json()[0]["content"] == "Keep this"
        assert (
            client.post("/workspaces/workspace/tasks", json={"title": "After upgrade"}).status_code
            == 201
        )
    engine.dispose()
