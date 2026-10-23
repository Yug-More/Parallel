"""Local-only durable worker: python worker.py [--once]. No external execution."""

import argparse
import time
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from actions import execute_once
from config import load_settings
from database import create_db_engine
from documents import ingest_once
from orchestration import run_once
from repositories import sync_once
from worker_health import heartbeat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Process at most one job/recovery/approval and exit"
    )
    args = parser.parse_args()
    settings = load_settings()
    engine = create_db_engine(settings.database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    worker_id, last_heartbeat = str(uuid4()), 0
    registered = False
    try:
        with engine.connect() as connection:
            if (
                "alembic_version" not in inspect(connection).get_table_names()
                or connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                != "0009_worker_health"
            ):
                raise RuntimeError("Run migrations before starting the worker")
        while True:
            if time.monotonic() - last_heartbeat > 10:
                heartbeat(factory, worker_id)
                registered, last_heartbeat = True, time.monotonic()
            worked = execute_once(factory) or run_once(factory) or ingest_once(factory)
            if not worked and settings.github_connector_enabled:
                worked = sync_once(factory)
            if args.once:
                break
            if not worked:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if registered:
            heartbeat(factory, worker_id, "stopped")
        engine.dispose()


if __name__ == "__main__":
    main()
