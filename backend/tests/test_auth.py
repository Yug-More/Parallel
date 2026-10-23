from dataclasses import replace
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from config import Settings, load_settings
from main import create_app


def test_authentication_logout_and_invalid_password(client, accounts):
    assert client.get("/me").status_code == 401
    user, profile = accounts()
    assert user.get("/me").json()["id"] == profile["id"]
    user.post("/auth/logout")
    assert user.get("/me").status_code == 401
    assert (
        user.post(
            "/auth/login", json={"email": "alice@example.test", "password": "wrong"}
        ).status_code
        == 401
    )
    assert (
        user.post(
            "/auth/login", json={"email": "ALICE@example.test", "password": "correct-password"}
        ).status_code
        == 200
    )
    assert (
        "httponly"
        in user.post(
            "/auth/login", json={"email": "alice@example.test", "password": "correct-password"}
        )
        .headers["set-cookie"]
        .lower()
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "short"},
        {"password": "a" * 73},
        {"password": "é" * 37},
        {"email": "invalid"},
        {"name": "  "},
        {"is_admin": True},
    ],
)
def test_registration_validation(client, changes):
    payload = {
        "email": "valid@example.test",
        "name": "Valid",
        "password": "correct-password",
        **changes,
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422
    assert all("input" not in error for error in response.json()["detail"])


def test_password_whitespace_is_significant(client):
    payload = {"email": "spaces@example.test", "name": "Space", "password": " padded password "}
    assert client.post("/auth/register", json=payload).status_code == 201
    client.post("/auth/logout")
    assert (
        client.post(
            "/auth/login", json={"email": payload["email"], "password": payload["password"].strip()}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={"email": payload["email"], "password": payload["password"]}
        ).status_code
        == 200
    )


def test_duplicate_email_role_and_name_collision(client):
    payload = {
        "email": "person@example.test",
        "name": "Same",
        "password": "correct-password",
        "role": "Engineering",
    }
    assert client.post("/auth/register", json=payload).json()["role"] == "Engineering"
    assert (
        client.post("/auth/register", json={**payload, "email": "PERSON@example.test"}).status_code
        == 409
    )
    assert (
        client.post("/auth/register", json={**payload, "email": "other@example.test"}).status_code
        == 201
    )


@pytest.mark.parametrize(
    "environment",
    [
        {"APP_ENV": "production"},
        {"SECRET_KEY": "dev-secret"},
        {"APP_ENV": "unknown"},
        {"CORS_ORIGINS": "*"},
        {"DATABASE_URL": "mysql://host/db"},
        {"APP_ENV": "production", "SECRET_KEY": "x" * 40, "CORS_ORIGINS": "http://example.test"},
    ],
)
def test_invalid_configuration(environment):
    with pytest.raises(ValueError):
        load_settings(environment)


def test_development_configuration_needs_no_provider_keys():
    settings = load_settings({})
    assert len(settings.secret_key) >= 32
    assert settings.openai_api_key is None
    assert not settings.secure_cookies


def test_production_cookie_is_secure(application):
    settings = replace(
        application.state.settings,
        environment="production",
        allowed_origins=("https://parallel.example",),
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.post(
            "/auth/register",
            json={"name": "Secure", "email": "secure@example.test", "password": "correct-password"},
        )
        assert response.status_code == 201
        assert "Secure" in response.headers["set-cookie"]


def test_tokens_require_correct_signature_expiry_and_subject(client, accounts, application):
    _, profile = accounts()
    valid = {"sub": profile["id"], "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    cases = [
        (valid, "dev-secret"),
        (
            {**valid, "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
            application.state.settings.secret_key,
        ),
        ({"sub": profile["id"]}, application.state.settings.secret_key),
    ]
    for payload, secret in cases:
        client.cookies.set("access_token", jwt.encode(payload, secret, algorithm="HS256"))
        assert client.get("/me").status_code == 401


def test_cross_origin_writes_rejected(client):
    assert (
        client.post("/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    )
    assert client.post("/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_startup_requires_migration(tmp_path):
    app = create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'unmigrated.db'}", secret_key="x" * 40)
    )
    with pytest.raises(RuntimeError, match="migration required"), TestClient(app):
        pass
