"""Disposable real HTTP server used only by Playwright; no provider credentials."""

import os
import sys
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import uvicorn
    from cryptography.fernet import Fernet

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
                local_index_enabled=True,
                embedding_provider="local",
                embedding_model="browser-fixture-not-trained",
                embedding_local_path=str(Path(temporary) / "no-model-download"),
                embedding_artifact_sha256="a" * 64,
                recovery_outbox_path=os.environ.get("PARALLEL_E2E_OUTBOX"),
                github_app_enabled=True,
                github_app_id=123,
                github_app_client_id="e2e-fixture-client",
                github_app_client_secret="e2e-fixture-secret",
                credential_encryption_key=Fernet.generate_key().decode(),
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

        import api.semantic
        import embedding_providers
        import github_app
        from recovery import LocalOutbox, deliver_once
        from semantic import index_once

        class FixtureEmbeddings:
            name = "trained-browser-fixture"
            model = "fabricated-vectors-not-quality-evidence"
            trained, external, usage_tokens = True, False, 0

            def embed(self, texts):
                return [[1.0, 0.0] for _ in texts]

        # Only this disposable test server injects fabricated vectors.
        embedding_providers.configured_provider = lambda _: FixtureEmbeddings()
        api.semantic.configured_provider = embedding_providers.configured_provider

        def fixture_private(path, *, token=None, data=None):
            if path == "/login/device/code":
                return {
                    "device_code": "e2e-device",
                    "user_code": "TEST-CODE",
                    "expires_in": 900,
                    "interval": 5,
                }
            if path == "/login/oauth/access_token":
                return {
                    "token_type": "bearer",
                    "access_token": "e2e-access",
                    "refresh_token": "e2e-refresh",
                    "expires_in": 28800,
                }
            if path.startswith("/user/installations?"):
                return {
                    "installations": [
                        {
                            "id": 42,
                            "app_id": 123,
                            "repository_selection": "selected",
                            "permissions": {
                                "metadata": "read",
                                "issues": "read",
                                "pull_requests": "read",
                            },
                        }
                    ]
                }
            if path.startswith("/user/installations/42/repositories?"):
                return {"repositories": [{"id": 99, "full_name": "parallel-example/private"}]}
            if path == "/repos/parallel-example/private":
                return {
                    "id": 99,
                    "private": True,
                    "full_name": "parallel-example/private",
                    "description": "Synthetic private test fixture",
                }
            if path.startswith("/repos/parallel-example/private/issues?"):
                return [
                    {
                        "number": 1,
                        "title": "Pilot rollback verification",
                        "body": "Verify the pilot rollback before release",
                        "state": "open",
                    }
                ]
            if path.startswith("/repos/parallel-example/private/pulls?"):
                return []
            raise SyncError("test_endpoint_unavailable")

        # Explicit test-only transport; no production fixture mode or real grant.
        github_app.request_json = fixture_private
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
                    app.state.session_factory, fixture_fetch, settings=app.state.settings
                ) or index_once(app.state.session_factory, settings=app.state.settings) or (
                    app.state.settings.recovery_outbox_path
                    and deliver_once(
                        app.state.session_factory,
                        LocalOutbox(app.state.settings.recovery_outbox_path),
                    )
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
