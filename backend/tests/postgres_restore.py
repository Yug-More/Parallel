"""CI-only real pg_dump/pg_restore drill in two exclusive synthetic databases.

Never restores into DATABASE_URL or drops an existing database. The container is
an explicit disposable PostgreSQL 16 CI service, not a production backup tool.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def snapshot(engine):
    from sqlalchemy import inspect, text

    result = {}
    with engine.connect() as db:
        for name in sorted(inspect(engine).get_table_names()):
            if not re.fullmatch(r"[a-z_]+", name):
                raise ValueError("Unexpected synthetic table name")
            rows = db.execute(text(f'SELECT * FROM "{name}"')).mappings().all()
            result[name] = sorted(
                json.dumps(dict(row), sort_keys=True, default=str) for row in rows
            )
    return result


def main():
    from fastapi.testclient import TestClient
    from sqlalchemy import make_url, text
    from test_documents import upload
    from test_intelligence import drain, start
    from test_native_actions import approve, proposal

    from actions import execute_once
    from config import Settings, load_settings
    from database import create_db_engine
    from documents import ingest_once
    from main import create_app
    from migrate import upgrade_database

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    args = parser.parse_args()
    settings = load_settings()
    url = make_url(settings.database_url)
    if (
        settings.environment != "test"
        or url.get_backend_name() != "postgresql"
        or url.database != "parallel_test"
        or not re.fullmatch(r"[a-zA-Z0-9_-]+", args.container)
    ):
        raise RuntimeError("Requires the explicit disposable parallel_test PostgreSQL service")
    service = create_db_engine(settings.database_url)
    names = ["parallel_drill_" + uuid4().hex for _ in range(2)]
    created, engines = [], []
    try:
        with service.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
            for name in names:
                # CREATE DATABASE fails on collision; no IF NOT EXISTS or reuse.
                db.execute(text(f'CREATE DATABASE "{name}"'))
                created.append(name)
        source_url, destination_url = [
            url.set(database=name).render_as_string(hide_password=False) for name in names
        ]
        upgrade_database(source_url)
        app = create_app(
            Settings(
                database_url=source_url,
                secret_key="test-only-restore-drill-secret-32-bytes",
                environment="test",
            )
        )
        with TestClient(app) as owner:
            assert (
                owner.post(
                    "/auth/register",
                    json={
                        "email": "restore@example.test",
                        "name": "Restore drill",
                        "password": "synthetic-password",
                    },
                ).status_code
                == 201
            )
            wid = owner.get("/workspaces").json()[0]["id"]
            assert upload(owner, wid).status_code == 202
            ingest_once(app.state.session_factory)
            start(owner, wid, agent_type="local.plan.v1", objective="Verify backup; Verify receipt")
            drain(app)
            assert approve(owner, wid, proposal(owner, wid)).status_code == 200
            assert execute_once(app.state.session_factory)
            assert proposal(owner, wid)["receipt"]["resources"]
        source, restored = [create_db_engine(value) for value in [source_url, destination_url]]
        engines.extend([source, restored])
        before = snapshot(source)
        with TemporaryDirectory(prefix="parallel-pg-drill-") as directory:
            path = Path(directory) / "synthetic.dump"
            env = {**os.environ, "PGPASSWORD": url.password or ""}
            prefix = ["docker", "exec", "-e", "PGPASSWORD", args.container]
            common = ["-h", "127.0.0.1", "-U", url.username or "parallel"]
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                subprocess.run(
                    prefix
                    + ["pg_dump", *common, "--format=custom", "--no-owner", "--no-acl", names[0]],
                    env=env,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=60,
                )
            with path.open("rb") as backup:
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        "-i",
                        "-e",
                        "PGPASSWORD",
                        args.container,
                        "pg_restore",
                        *common,
                        "--exit-on-error",
                        "--no-owner",
                        "--no-acl",
                        "--dbname",
                        names[1],
                    ],
                    env=env,
                    stdin=backup,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=60,
                )
            assert snapshot(restored) == before, "Restoration changed synthetic rows or receipts"
            assert snapshot(source) == before, "The source changed during the drill"
            upgrade_database(destination_url)
            assert snapshot(restored) == before, "Repeated migration changed restored records"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(
            json.dumps(
                {
                    "drill": "isolated_postgres_restore",
                    "tables": len(before),
                    "rows": sum(map(len, before.values())),
                    "backup_sha256": digest,
                    "source_unchanged": True,
                    "receipts_preserved": True,
                    "restored_migration_verified": True,
                }
            )
        )
    finally:
        for engine in engines:
            engine.dispose()
        with service.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
            for name in created:
                assert name.startswith("parallel_drill_") and re.fullmatch(
                    r"parallel_drill_[a-f0-9]{32}", name
                )
                db.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        service.dispose()


if __name__ == "__main__":
    main()
