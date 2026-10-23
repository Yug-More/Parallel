"""Run migrations explicitly; startup never changes application schema."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_database(url=None, revision="head"):
    config = Config(str(Path(__file__).with_name("alembic.ini")))
    if url:
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, revision)


if __name__ == "__main__":
    upgrade_database()
