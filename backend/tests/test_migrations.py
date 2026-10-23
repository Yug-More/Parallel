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


@pytest.mark.parametrize("role", ["member", "missing"])
def test_phase1b_upgrade_refuses_inconsistent_ownership_without_changing_data(tmp_path, role):
    url = f"sqlite:///{tmp_path / 'invalid_owner.db'}"
    upgrade_database(url, "0002_workspaces")
    engine = create_db_engine(url)
    with engine.begin() as db:
        db.execute(
            text("INSERT INTO users (id,email,name) VALUES ('owner','owner@example.test','Owner')")
        )
        db.execute(
            text(
                "INSERT INTO workspaces (id,name,owner_id,created_at) VALUES ('space','Preserve','owner','2026-01-01')"
            )
        )
        if role != "missing":
            db.execute(
                text(
                    "INSERT INTO workspace_memberships (workspace_id,user_id,role,created_at) VALUES ('space','owner',:role,'2026-01-01')"
                ),
                {"role": role},
            )
    with pytest.raises(RuntimeError, match="Inconsistent workspace ownership"):
        upgrade_database(url)
    with engine.connect() as db:
        assert db.execute(text("SELECT name FROM workspaces")).scalar() == "Preserve"
        assert "revision" not in {
            column["name"] for column in inspect(db).get_columns("workspaces")
        }
    engine.dispose()


def test_phase1b_upgrade_preserves_every_existing_table(tmp_path):
    from datetime import timedelta

    from sqlalchemy.orm import Session

    from models import (
        Activity,
        AuthSession,
        Invitation,
        Membership,
        Task,
        TaskDependency,
        User,
        UserCredential,
        utc_now,
    )

    url = f"sqlite:///{tmp_path / 'phase1b-upgrade.db'}"
    upgrade_database(url, "0003_collaboration")
    engine = create_db_engine(url)
    with Session(engine) as db:
        db.add_all(
            [
                User(id="owner", email="owner@example.test", name="Owner"),
                User(id="recipient", email="recipient@example.test", name="Recipient"),
            ]
        )
        db.flush()
        db.add(UserCredential(user_id="owner", password_hash=hash_password("keep-password")))
        db.execute(
            text(
                "INSERT INTO workspaces (id,name,owner_id,created_at) VALUES (:id,:name,:owner,:created)"
            ),
            {"id": "space", "name": "Preserve all records", "owner": "owner", "created": utc_now()},
        )
        db.flush()
        db.add(Membership(workspace_id="space", user_id="owner", role="owner"))
        db.flush()
        db.add_all(
            [
                Task(
                    id=tid,
                    workspace_id="space",
                    creator_id="owner",
                    assignee_id="owner",
                    title=tid,
                    status="todo",
                    priority="high",
                )
                for tid in ["task1", "task2"]
            ]
        )
        db.flush()
        db.add(TaskDependency(workspace_id="space", task_id="task2", depends_on_id="task1"))
        db.add(
            Invitation(
                id="invite",
                workspace_id="space",
                recipient_id="recipient",
                inviter_id="owner",
                status="pending",
                expires_at=utc_now() + timedelta(days=7),
            )
        )
        db.add(
            AuthSession(id="a" * 64, user_id="owner", expires_at=utc_now() + timedelta(hours=24))
        )
        db.execute(
            text(
                "INSERT INTO messages (id,workspace_id,user_id,sender_id,sender_name,role,content,created_at) VALUES ('message','space','owner','owner','Owner','user','Preserve private history',:created)"
            ),
            {"created": utc_now()},
        )
        db.add(
            Activity(
                id="activity",
                workspace_id="space",
                user_id="owner",
                user_name="Owner",
                summary="Preserve activity",
            )
        )
        db.commit()
    tables = [
        "users",
        "user_credentials",
        "workspaces",
        "workspace_memberships",
        "tasks",
        "task_dependencies",
        "workspace_invitations",
        "auth_sessions",
        "messages",
        "activities",
    ]

    original_columns = {
        table: ",".join(column["name"] for column in inspect(engine).get_columns(table))
        for table in tables
    }

    def snapshot():
        with engine.connect() as db:
            return {
                table: db.execute(text(f"SELECT {original_columns[table]} FROM {table}")).all()
                for table in tables
            }

    before = snapshot()
    upgrade_database(url)
    upgrade_database(url)
    assert snapshot() == before
    assert set(inspect(engine).get_table_names()) >= {
        "decisions",
        "decision_revisions",
        "decision_sources",
        "agent_runs",
        "run_events",
        "approvals",
        "workspace_visits",
    }
    with engine.connect() as db:
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    engine.dispose()


def test_intelligence_migration_uses_portable_postgres_boolean_default():
    import importlib.util
    import io
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).parents[1] / "migrations/versions/0004_intelligence.py"
    spec = importlib.util.spec_from_file_location("intelligence_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    sql = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": sql}
    )
    with Operations.context(context):
        migration.upgrade()
    assert "publish BOOLEAN DEFAULT false NOT NULL" in sql.getvalue()
    assert "BOOLEAN DEFAULT 0" not in sql.getvalue()


def test_populated_phase3_upgrade_preserves_records_and_receipts(tmp_path):
    from datetime import datetime, timedelta

    from sqlalchemy import MetaData, select

    url = f"sqlite:///{tmp_path / 'phase3-upgrade.db'}"
    upgrade_database(url, "0004_intelligence")
    engine = create_db_engine(url)
    metadata = MetaData()
    metadata.reflect(engine)
    now = datetime(2026, 10, 1)
    with engine.begin() as db:
        db.execute(
            metadata.tables["users"].insert(),
            {"id": "owner", "email": "owner@example.test", "name": "Owner"},
        )
        db.execute(
            metadata.tables["workspaces"].insert(),
            {"id": "space", "owner_id": "owner", "name": "Phase 3 project", "created_at": now},
        )
        db.execute(
            metadata.tables["workspace_memberships"].insert(),
            {"workspace_id": "space", "user_id": "owner", "role": "owner", "created_at": now},
        )
        db.execute(
            metadata.tables["messages"].insert(),
            {
                "id": "report",
                "workspace_id": "space",
                "user_id": "owner",
                "sender_id": "local.status.v1",
                "sender_name": "Project status",
                "role": "assistant",
                "content": "Retain approved report",
                "created_at": now,
            },
        )
        db.execute(
            metadata.tables["decisions"].insert(),
            {
                "id": "choice",
                "workspace_id": "space",
                "creator_id": "owner",
                "title": "Preserve choices",
                "context": "Prior work",
                "statement": "Retain provenance",
                "rationale": "Auditability",
                "alternatives": "",
                "tradeoffs": "",
                "status": "accepted",
                "version": 1,
                "created_at": now,
                "updated_at": now,
            },
        )
        db.execute(
            metadata.tables["decision_revisions"].insert(),
            {
                "decision_id": "choice",
                "workspace_id": "space",
                "actor_id": "owner",
                "version": 1,
                "reason": "Initial decision",
                "snapshot": {"title": "Preserve choices", "statement": "Retain provenance"},
                "created_at": now,
            },
        )
        db.execute(
            metadata.tables["decision_sources"].insert(),
            {
                "workspace_id": "space",
                "decision_id": "choice",
                "revision": 1,
                "kind": "message",
                "source_id": "report",
                "snapshot": {"body": "Retain approved report"},
            },
        )
        db.execute(
            metadata.tables["workspace_visits"].insert(),
            {"workspace_id": "space", "user_id": "owner", "through": now},
        )
        db.execute(
            metadata.tables["agent_runs"].insert(),
            {
                "id": "run",
                "workspace_id": "space",
                "initiator_id": "owner",
                "agent_type": "local.status.v1",
                "objective": "Preserve outcome",
                "request_hash": "a" * 64,
                "input_refs": [],
                "state": "completed",
                "attempt": 1,
                "context": {"fingerprint": "before"},
                "outcome": {"summary": "Stored report"},
                "created_at": now,
                "completed_at": now,
            },
        )
        db.execute(
            metadata.tables["approvals"].insert(),
            {
                "id": "approval",
                "workspace_id": "space",
                "run_id": "run",
                "action": "publish_report",
                "payload": {"content": "Retain approved report"},
                "payload_hash": "b" * 64,
                "state": "executed",
                "approver_id": "owner",
                "message_id": "report",
                "created_at": now,
                "expires_at": now + timedelta(days=1),
                "executed_at": now,
            },
        )
        db.execute(
            metadata.tables["run_events"].insert(),
            {
                "id": "event",
                "workspace_id": "space",
                "run_id": "run",
                "event": "published",
                "detail": {"message_id": "report"},
                "created_at": now,
            },
        )

    def snapshot():
        with engine.connect() as db:
            return {
                name: db.execute(select(table).order_by(*table.primary_key.columns)).all()
                for name, table in metadata.tables.items()
                if name != "alembic_version"
            }

    before = snapshot()
    upgrade_database(url)
    upgrade_database(url)
    assert snapshot() == before
    with engine.connect() as db:
        assert db.execute(text("SELECT knowledge_epoch FROM workspaces")).scalar() == 0
        assert db.execute(text("SELECT knowledge_epoch FROM messages")).scalar() is None
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    engine.dispose()


@pytest.mark.parametrize(
    "filename",
    [
        "0005_documents.py",
        "0006_repositories.py",
        "0007_answers.py",
        "0008_actions.py",
        "0009_worker_health.py",
    ],
)
def test_connected_migrations_compile_portable_postgres_ddl(filename):
    import importlib.util
    import io
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).parents[1] / "migrations/versions" / filename
    spec = importlib.util.spec_from_file_location("connected_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    sql = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": sql}
    )
    with Operations.context(context):
        migration.upgrade()
    assert "BOOLEAN DEFAULT 0" not in sql.getvalue()
    assert "CREATE TABLE" in sql.getvalue()
