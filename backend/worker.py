"""Local-only durable worker: python worker.py [--once]. No external execution."""

import argparse
import logging
import time
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from actions import execute_once
from config import load_settings
from database import create_db_engine
from documents import ingest_once
from github_app import expire_workspace, maintain_private
from models import RepositoryConnection
from orchestration import run_once
from recovery import LocalOutbox, deliver_once, maintain_operational_records
from repositories import sync_once
from semantic import index_once
from worker_health import HeartbeatSupervisor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Process at most one job/recovery/approval and exit"
    )
    args = parser.parse_args()
    settings = load_settings()
    engine = create_db_engine(settings.database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    worker_id = str(uuid4())
    supervisor = None
    cooldowns = {}
    last_maintenance = 0
    cursor = 0
    try:
        with engine.connect() as connection:
            if (
                "alembic_version" not in inspect(connection).get_table_names()
                or connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                != "0018_sync_checkpoints"
            ):
                raise RuntimeError("Run migrations before starting the worker")
        supervisor = HeartbeatSupervisor(factory, worker_id)
        supervisor.__enter__()
        while True:
            if time.monotonic() - last_maintenance >= 60:
                maintain_operational_records(factory)
                last_maintenance = time.monotonic()
            with factory() as db:
                ids = (
                    db.query(RepositoryConnection.workspace_id)
                    .filter_by(active=True, auth_mode="github_app_user")
                    .distinct()
                    .all()
                )
                for (wid,) in ids:
                    expire_workspace(db, wid)
                db.commit()
            if settings.github_app_enabled:
                maintain_private(factory)
            queues = [
                lambda: execute_once(factory),
                lambda: run_once(factory),
                lambda: ingest_once(factory),
            ]
            if settings.github_connector_enabled:
                queues.append(lambda: sync_once(factory, settings=settings))
            if settings.local_index_enabled or settings.embedding_provider != "disabled":
                queues.append(lambda: index_once(factory, settings=settings))
            if settings.recovery_outbox_path:
                queues.append(
                    lambda: deliver_once(factory, LocalOutbox(settings.recovery_outbox_path))
                )
            worked = False
            for step in range(len(queues)):
                index = (cursor + step) % len(queues)
                if cooldowns.get(index, 0) > time.monotonic():
                    continue
                try:
                    if queues[index]():
                        cursor, worked = (index + 1) % len(queues), True
                        break
                except Exception:
                    logging.getLogger(__name__).warning("worker_queue_failed queue=%d", index)
                    cooldowns[index] = time.monotonic() + 30
                    cursor = (index + 1) % len(queues)
            if args.once:
                break
            if not worked:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if supervisor:
            supervisor.__exit__(None, None, None)
        engine.dispose()


if __name__ == "__main__":
    main()
