"""CI-only integration check against the disposable PostgreSQL service."""

import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from fastapi.testclient import TestClient

    from main import create_app

    with TestClient(create_app()) as client:
        email = f"{uuid4()}@postgres.example.test"
        response = client.post(
            "/auth/register",
            json={"name": "Postgres", "email": email, "password": "postgres-test-password"},
        )
        assert response.status_code == 201, response.text
        workspace_id = client.get("/workspaces").json()[0]["id"]
        assert (
            client.post(
                f"/workspaces/{workspace_id}/messages", json={"content": "PostgreSQL persistence"}
            ).status_code
            == 201
        )
        client.post("/auth/logout")
        assert client.get(f"/workspaces/{workspace_id}/messages").status_code == 401
        assert (
            client.post(
                "/auth/login", json={"email": email, "password": "postgres-test-password"}
            ).status_code
            == 200
        )
        assert (
            client.get(f"/workspaces/{workspace_id}/messages").json()[0]["content"]
            == "PostgreSQL persistence"
        )
    print("PostgreSQL registration, messaging, isolation and persistence passed")


if __name__ == "__main__":
    main()
