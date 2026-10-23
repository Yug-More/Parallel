"""Upgrade a disposable PostgreSQL schema containing actual Phase 1A records."""

import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from sqlalchemy import make_url, text

    from config import load_settings
    from database import create_db_engine
    from migrate import upgrade_database

    settings = load_settings()
    if settings.environment != "test" or "parallel_test" not in settings.database_url:
        raise RuntimeError("Requires the disposable CI test database and APP_ENV=test")
    schema = "upgrade_" + uuid4().hex
    engine = create_db_engine(settings.database_url)
    with engine.begin() as db:
        db.execute(text(f"CREATE SCHEMA {schema}"))
    url = (
        make_url(settings.database_url)
        .update_query_dict({"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    upgrade_database(url, "0002_workspaces")
    isolated = create_db_engine(url)
    with isolated.begin() as db:
        db.execute(
            text("INSERT INTO users (id,email,name) VALUES ('owner','owner@example.test','Owner')")
        )
        db.execute(
            text(
                "INSERT INTO workspaces (id,name,owner_id,created_at) VALUES ('space','Preserved','owner','2026-01-01')"
            )
        )
        db.execute(
            text(
                "INSERT INTO workspace_memberships (workspace_id,user_id,role,created_at) VALUES ('space','owner','owner','2026-01-01')"
            )
        )
        db.execute(
            text(
                "INSERT INTO messages (id,user_id,workspace_id,sender_id,sender_name,role,content) VALUES ('message','owner','space','owner','Owner','user','Preserve PostgreSQL history')"
            )
        )
    upgrade_database(url)
    upgrade_database(url)
    with isolated.connect() as db:
        assert (
            db.execute(text("SELECT content FROM messages")).scalar()
            == "Preserve PostgreSQL history"
        )
        assert db.execute(text("SELECT COUNT(*) FROM workspace_memberships")).scalar() == 1
        assert db.execute(text("SELECT revision FROM workspaces")).scalar() == 0
        assert db.execute(text("SELECT COUNT(*) FROM auth_sessions")).scalar() == 0
    isolated.dispose()
    engine.dispose()
    print("PostgreSQL Phase 1A upgrade preserved workspace membership and messages")


if __name__ == "__main__":
    main()
