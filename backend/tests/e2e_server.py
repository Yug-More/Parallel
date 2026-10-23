"""Disposable real HTTP server used only by Playwright; no provider credentials."""

import sys
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
                allowed_origins=("http://127.0.0.1:15175",),
            )
        )
        uvicorn.run(app, host="127.0.0.1", port=18001)


if __name__ == "__main__":
    main()
