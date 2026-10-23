"""CI-only PostgreSQL collaboration, constraints and concurrency verification."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from fastapi.testclient import TestClient

    from config import load_settings
    from main import create_app

    settings = load_settings()
    if settings.environment != "test" or "parallel_test" not in settings.database_url:
        raise RuntimeError("Run only against the disposable CI test database with APP_ENV=test")
    app = create_app(settings)
    suffix = uuid4().hex
    with TestClient(app) as owner, TestClient(app) as member:
        for client, name in [(owner, "Owner"), (member, "Member")]:
            assert (
                client.post(
                    "/auth/register",
                    json={
                        "name": name,
                        "email": f"{name}-{suffix}@example.test",
                        "password": "postgres-test-password",
                    },
                ).status_code
                == 201
            )
        member_id = member.get("/me").json()["id"]
        wid = owner.post("/workspaces", json={"name": "PostgreSQL collaboration"}).json()["id"]
        invitation = owner.post(
            f"/workspaces/{wid}/invitations", json={"email": f"Member-{suffix}@example.test"}
        ).json()
        assert member.post(f"/invitations/{invitation['id']}/accept").status_code == 200
        assert (
            member.post(
                f"/workspaces/{wid}/messages", json={"content": "PostgreSQL persisted message"}
            ).status_code
            == 201
        )
        item = owner.post(
            f"/workspaces/{wid}/tasks", json={"title": "PostgreSQL task", "assignee_id": member_id}
        ).json()

        def edit(title):
            client = TestClient(app)
            client.cookies.update(member.cookies)
            return client.patch(
                f"/workspaces/{wid}/tasks/{item['id']}", json={"version": 1, "title": title}
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(edit, ["Concurrent A", "Concurrent B"])) == [200, 409]
        assert owner.delete(f"/workspaces/{wid}/members/{member_id}").status_code == 200
        assert member.get(f"/workspaces/{wid}/tasks").status_code == 404
        assert owner.get(f"/workspaces/{wid}/tasks/{item['id']}").json()["assignee_id"] is None
        copied = TestClient(app)
        copied.cookies.update(owner.cookies)
        assert owner.post("/auth/logout-all").status_code == 200
        assert copied.get("/me").status_code == 401
        assert (
            owner.post(
                "/auth/login",
                json={
                    "email": f"Owner-{suffix}@example.test",
                    "password": "postgres-test-password",
                },
            ).status_code
            == 200
        )
        assert (
            owner.get(f"/workspaces/{wid}/messages").json()[0]["content"]
            == "PostgreSQL persisted message"
        )
    print(
        "PostgreSQL invitations, task concurrency, removal, persistence and session revocation passed"
    )


if __name__ == "__main__":
    main()
