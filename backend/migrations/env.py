from alembic import context

import models  # noqa: F401 -- registers ORM metadata
from config import load_settings
from database import Base, create_db_engine

config = context.config
target_metadata = Base.metadata
url = config.get_main_option("sqlalchemy.url") or load_settings().database_url

if context.is_offline_mode():
    raise RuntimeError("Offline migration is unsupported: legacy schema inspection is required")
else:
    engine = create_db_engine(url)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
