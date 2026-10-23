import os
import socket
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text

from config import Settings
from database import create_db_engine
from main import create_app
from migrate import upgrade_database


@pytest.fixture(autouse=True)
def no_paid_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("Tests must never access external services")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def application(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    service, schema = None, None
    if os.environ.get("PARALLEL_TEST_POSTGRES") == "true":
        configured = make_url(os.environ["DATABASE_URL"])
        if (
            os.environ.get("APP_ENV") != "test"
            or configured.get_backend_name() != "postgresql"
            or configured.database != "parallel_test"
        ):
            raise RuntimeError("PostgreSQL tests require the disposable parallel_test service")
        service = create_db_engine(configured.render_as_string(hide_password=False))
        schema = "hardening_" + uuid4().hex
        with service.begin() as db:
            db.execute(text(f"CREATE SCHEMA {schema}"))
        url = configured.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
            hide_password=False
        )
    upgrade_database(url)
    app = create_app(
        Settings(
            database_url=url,
            secret_key="test-only-session-signing-key-32-bytes",
            environment="test",
        )
    )
    try:
        yield app
    finally:
        app.state.session_factory.kw["bind"].dispose()
        if service is not None:
            with service.begin() as db:
                db.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            service.dispose()


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client


@pytest.fixture
def accounts(application):
    def create(email="alice@example.test", name="Alice"):
        client = TestClient(application)
        response = client.post(
            "/auth/register", json={"email": email, "name": name, "password": "correct-password"}
        )
        assert response.status_code == 201, response.text
        return client, response.json()

    return create
