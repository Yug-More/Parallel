import socket

import pytest
from fastapi.testclient import TestClient

from config import Settings
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
    upgrade_database(url)
    return create_app(
        Settings(
            database_url=url,
            secret_key="test-only-session-signing-key-32-bytes",
            environment="test",
        )
    )


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
