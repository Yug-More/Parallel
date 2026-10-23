"""Local-only durable worker: python worker.py [--once]. No external execution."""

import argparse
import time

from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from config import load_settings
from database import create_db_engine
from orchestration import run_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Process at most one job/recovery/approval and exit"
    )
    args = parser.parse_args()
    engine = create_db_engine(load_settings().database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with engine.connect() as connection:
            if (
                "alembic_version" not in inspect(connection).get_table_names()
                or connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                != "0004_intelligence"
            ):
                raise RuntimeError("Run migrations before starting the worker")
        while True:
            worked = run_once(factory)
            if args.once:
                break
            if not worked:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
