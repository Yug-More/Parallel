"""Database construction is explicit; importing models never opens a database."""

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def create_db_engine(url):
    kwargs = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=kwargs, pool_pre_ping=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def get_db(request: Request):
    with request.app.state.session_factory() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise
