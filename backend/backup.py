"""Create a consistent SQLite backup at a new path; never overwrite a backup.

PostgreSQL operators should use pg_dump and test restoration separately.
"""

import argparse
import os
import sqlite3
from pathlib import Path

from sqlalchemy.engine import make_url

from config import load_settings


def backup_sqlite(database_url, output):
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("Requires a file-backed SQLite database; use pg_dump for PostgreSQL")
    source, destination = Path(url.database).resolve(), Path(output).resolve()
    if not source.is_file() or source == destination:
        raise ValueError("Source must exist and differ from the backup path")
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    # Keep any failed backup for diagnosis; never delete or replace user files.
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(destination) as backup:
            original.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = backup_sqlite(load_settings().database_url, args.output)
    print(f"SQLite backup verified: {result}")


if __name__ == "__main__":
    main()
