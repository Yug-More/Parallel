"""Disposable real HTTP server used only by Playwright; no provider credentials."""

import sys
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import uvicorn

    from config import Settings
    from main import create_app
    from migrate import upgrade_database

    with TemporaryDirectory(prefix="parallel-e2e-") as temporary:
        url = f"sqlite:///{temporary}/e2e.db"
        upgrade_database(url)
        app = create_app(
            Settings(
                database_url=url,
                secret_key="e2e-only-session-signing-key-32-bytes",
                environment="test",
                github_connector_enabled=True,
                allowed_origins=("http://127.0.0.1:15175",),
            )
        )
        import logging
        import time

        logging.getLogger("parallel.http").setLevel(logging.WARNING)

        from actions import execute_once
        from documents import ingest_once
        from orchestration import run_once
        from repositories import SyncError, fetch_repository, sync_once
        from worker_health import heartbeat

        def fixture_fetch(repository):
            # Test-only provider fixture; production code has no fixture switch.
            if repository != "parallel-example/demo":
                raise SyncError("test_repository_unavailable")

            def read(path):
                if "?" not in path:
                    return {
                        "private": False,
                        "full_name": repository,
                        "description": "Synthetic browser fixture",
                    }
                if "/issues?" in path:
                    return [
                        {
                            "number": 1,
                            "title": "Revocable sessions",
                            "body": "Review logout behavior before release.",
                            "state": "open",
                        }
                    ]
                return []

            return fetch_repository(repository, read)

        stopped = threading.Event()

        def worker():
            last_heartbeat = 0
            while not stopped.is_set():
                if time.monotonic() - last_heartbeat > 10:
                    heartbeat(app.state.session_factory, "e2e-worker")
                    last_heartbeat = time.monotonic()
                execute_once(app.state.session_factory) or run_once(
                    app.state.session_factory
                ) or ingest_once(app.state.session_factory) or sync_once(
                    app.state.session_factory, fixture_fetch
                )
                stopped.wait(0.2)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            uvicorn.run(app, host="127.0.0.1", port=18001)
        finally:
            stopped.set()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
