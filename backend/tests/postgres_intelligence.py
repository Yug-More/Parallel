"""CI-only PostgreSQL provenance, concurrent revisions, runs and Phase 1B preservation."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from datetime import timedelta

    from fastapi.testclient import TestClient
    from sqlalchemy import inspect, make_url, text
    from sqlalchemy.orm import Session

    from config import Settings, load_settings
    from database import create_db_engine
    from main import create_app
    from migrate import upgrade_database
    from models import (
        AuthSession,
        Invitation,
        Membership,
        Task,
        TaskDependency,
        utc_now,
    )
    from orchestration import run_once

    settings = load_settings()
    if settings.environment != "test" or "parallel_test" not in settings.database_url:
        raise RuntimeError("Requires APP_ENV=test and the disposable parallel_test service")
    schema = "intelligence_" + uuid4().hex
    service = create_db_engine(settings.database_url)
    with service.begin() as db:
        db.execute(text(f"CREATE SCHEMA {schema}"))
    url = (
        make_url(settings.database_url)
        .update_query_dict({"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    upgrade_database(url, "0003_collaboration")
    engine = create_db_engine(url)
    with Session(engine) as db:
        # Seed the actual historical columns, independent of new ORM fields.
        db.execute(
            text(
                "INSERT INTO users (id,email,name,created_at,last_seen_at) VALUES (:id,:email,:name,:created,:created)"
            ),
            [
                {
                    "id": "keep",
                    "email": "keep@example.test",
                    "name": "Preserved",
                    "created": utc_now(),
                },
                {
                    "id": "invitee",
                    "email": "invitee@example.test",
                    "name": "Invitee",
                    "created": utc_now(),
                },
            ],
        )
        db.flush()
        db.execute(
            text(
                "INSERT INTO workspaces (id,name,owner_id,created_at) VALUES ('space','Phase 1B preservation','keep',:created)"
            ),
            {"created": utc_now()},
        )
        db.flush()
        db.add(Membership(workspace_id="space", user_id="keep", role="owner"))
        db.flush()
        for tid in ["parent", "dependent"]:
            db.add(
                Task(
                    id=tid,
                    workspace_id="space",
                    creator_id="keep",
                    assignee_id="keep",
                    title=tid,
                    status="todo",
                    priority="high",
                )
            )
        db.flush()
        db.add(TaskDependency(workspace_id="space", task_id="dependent", depends_on_id="parent"))
        db.add(
            Invitation(
                id="invitation",
                workspace_id="space",
                recipient_id="invitee",
                inviter_id="keep",
                status="pending",
                expires_at=utc_now() + timedelta(days=7),
            )
        )
        db.add(AuthSession(id="a" * 64, user_id="keep", expires_at=utc_now() + timedelta(hours=24)))
        db.commit()
    tables = [
        "users",
        "workspaces",
        "workspace_memberships",
        "tasks",
        "task_dependencies",
        "workspace_invitations",
        "auth_sessions",
    ]

    original_columns = {
        table: ",".join(column["name"] for column in inspect(engine).get_columns(table))
        for table in tables
    }

    def snapshot():
        with engine.connect() as db:
            return {
                table: db.execute(
                    text(f"SELECT {original_columns[table]} FROM {table} ORDER BY 1")
                ).all()
                for table in tables
            }

    before = snapshot()
    upgrade_database(url)
    upgrade_database(url)
    assert snapshot() == before
    engine.dispose()
    app = create_app(
        Settings(
            database_url=url,
            secret_key="test-only-postgres-intelligence-signing-key",
            environment="test",
        )
    )
    with TestClient(app) as owner:
        assert (
            owner.post(
                "/auth/register",
                json={
                    "name": "Owner",
                    "email": "new-owner@example.test",
                    "password": "postgres-test-password",
                },
            ).status_code
            == 201
        )
        wid = owner.post("/workspaces", json={"name": "Postgres intelligence"}).json()["id"]
        task = owner.post(f"/workspaces/{wid}/tasks", json={"title": "Evaluate PostgreSQL"}).json()
        decision = owner.post(
            f"/workspaces/{wid}/decisions",
            json={
                "title": "Database architecture",
                "statement": "Use existing SQL storage",
                "status": "accepted",
                "sources": [{"kind": "task", "id": task["id"]}],
            },
        ).json()

        def revise(title):
            with TestClient(app) as client:
                client.cookies.update(owner.cookies)
                return client.patch(
                    f"/workspaces/{wid}/decisions/{decision['id']}",
                    json={
                        "version": 1,
                        "title": title,
                        "statement": "Use existing SQL storage",
                        "status": "accepted",
                        "sources": [],
                        "reason": "Concurrent correction",
                    },
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(revise, ["SQL persistence", "SQL databases"])) == [200, 409]
        assert (
            owner.get(f"/workspaces/{wid}/decisions/{decision['id']}/history").json()["total"] == 2
        )
        assert owner.get(f"/workspaces/{wid}/knowledge?q=SQL&kind=decision").json()["total"] == 1
        run = owner.post(
            f"/workspaces/{wid}/runs",
            json={
                "agent_type": "local.handoff.v1",
                "objective": "Prepare database handoff",
                "publish": True,
                "idempotency_key": "postgres-run-0001",
            },
        ).json()
        for _ in range(10):
            if not run_once(app.state.session_factory):
                break
        saved = owner.get(f"/workspaces/{wid}/runs/{run['id']}").json()
        assert saved["state"] == "waiting_for_approval" and len(saved["children"]) == 2
        approval = saved["approval"]
        assert (
            owner.post(
                f"/workspaces/{wid}/approvals/{approval['id']}/approve",
                json={"payload_hash": approval["payload_hash"]},
            ).status_code
            == 200
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: run_once(app.state.session_factory), range(2)))
        saved = owner.get(f"/workspaces/{wid}/runs/{run['id']}").json()
        assert saved["state"] == "completed" and saved["approval"]["state"] == "executed"
        assert len(owner.get(f"/workspaces/{wid}/messages").json()) == 1
    service.dispose()
    print(
        "PostgreSQL Phase 1B preservation, lexical retrieval, decision race, delegated runs and exact-once approval publication passed"
    )


if __name__ == "__main__":
    main()
