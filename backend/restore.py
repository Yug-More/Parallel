"""Restore a SQLite backup to a NEW path and validate schema/integrity.

Never replaces or opens the configured live database for writing. Stop services
and choose a private disposable destination before an operator cutover.
"""

import argparse
from pathlib import Path

from sqlalchemy import text

from backup import backup_sqlite
from database import create_db_engine
from migrate import upgrade_database


def restore_sqlite(source, output):
    restored = backup_sqlite(f"sqlite:///{Path(source).resolve()}", output)
    upgrade_database(f"sqlite:///{restored}")
    engine = create_db_engine(f"sqlite:///{restored}")
    try:
        with engine.connect() as db:
            if (
                db.execute(text("PRAGMA integrity_check")).scalar() != "ok"
                or db.execute(text("PRAGMA foreign_key_check")).all()
            ):
                raise RuntimeError("Restored database failed integrity/foreign-key verification")
    finally:
        engine.dispose()
    return restored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"Restored and verified new database: {restore_sqlite(args.source, args.output)}")


if __name__ == "__main__":
    main()
