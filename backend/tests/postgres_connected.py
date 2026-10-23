"""CI-only connected-source and native-action checks on disposable PostgreSQL."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import base64

    from fastapi.testclient import TestClient
    from sqlalchemy import make_url, text

    from actions import execute_once
    from config import Settings, load_settings
    from database import create_db_engine
    from documents import ingest_once
    from main import create_app
    from migrate import upgrade_database
    from orchestration import run_once
    from repositories import sync_once

    settings = load_settings()
    if settings.environment != "test" or "parallel_test" not in settings.database_url:
        raise RuntimeError("Requires APP_ENV=test and disposable parallel_test PostgreSQL")
    schema = "connected_" + uuid4().hex
    service = create_db_engine(settings.database_url)
    with service.begin() as db:
        db.execute(text(f"CREATE SCHEMA {schema}"))
    url = (
        make_url(settings.database_url)
        .update_query_dict({"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    try:
        upgrade_database(url)
        upgrade_database(url)
        app = create_app(
            Settings(
                database_url=url,
                secret_key="test-only-postgres-connected-signing-key-32-bytes",
                environment="test",
                github_connector_enabled=True,
            )
        )
        with TestClient(app) as owner, TestClient(app) as other:
            for client, name in [(owner, "Owner"), (other, "Other")]:
                assert (
                    client.post(
                        "/auth/register",
                        json={
                            "name": name,
                            "email": name + "@example.test",
                            "password": "test-password-long",
                        },
                    ).status_code
                    == 201
                )
            wid = owner.post("/workspaces", json={"name": "Connected PG"}).json()["id"]
            doc = owner.post(
                f"/workspaces/{wid}/documents",
                json={
                    "filename": "context.md",
                    "title": "Context",
                    "content_base64": base64.b64encode(
                        b"Review revocable sessions before release."
                    ).decode(),
                },
            ).json()
            assert ingest_once(app.state.session_factory)
            evidence = owner.get(f"/workspaces/{wid}/knowledge?q=revocable&kind=document").json()
            assert evidence["total"] == 1
            source_id = evidence["items"][0]["id"]
            assert other.get(f"/workspaces/{wid}/sources/document/{source_id}").status_code == 404
            response = owner.post(
                f"/workspaces/{wid}/answers",
                json={
                    "question": "revocable sessions",
                    "idempotency_key": "pg-answer-request-0001",
                },
            )
            assert response.status_code == 201 and response.json()["state"] == "completed", (
                response.text
            )
            connection = owner.post(
                f"/workspaces/{wid}/connections", json={"repository": "synthetic/project"}
            ).json()
            assert sync_once(
                app.state.session_factory,
                lambda _: [
                    {
                        "provider_id": "issues:1",
                        "record_type": "issues",
                        "title": "Revocable sessions",
                        "body": "Review policy",
                        "status": "open",
                        "original_url": "https://github.com/synthetic/project/issues/1",
                    }
                ],
            )
            run = owner.post(
                f"/workspaces/{wid}/runs",
                json={
                    "agent_type": "local.delivery.v1",
                    "objective": "Review revocable sessions; Verify release",
                    "idempotency_key": "pg-native-plan-0001",
                },
            ).json()
            for _ in range(10):
                if not run_once(app.state.session_factory):
                    break
            result = owner.get(f"/workspaces/{wid}/runs/{run['id']}").json()
            assert result["state"] == "completed" and len(result["children"]) == 2, result
            proposal = owner.get(f"/workspaces/{wid}/action-proposals").json()["items"][0]
            response = owner.post(
                f"/workspaces/{wid}/action-proposals/{proposal['id']}/approve",
                json={"payload_hash": proposal["payload_hash"]},
            )
            assert response.status_code == 200, response.text
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _: execute_once(app.state.session_factory), range(2)))
            tasks = owner.get(f"/workspaces/{wid}/tasks").json()
            assert tasks["total"] == 2 and all(t["status"] == "todo" for t in tasks["items"])
            receipt = owner.get(f"/workspaces/{wid}/action-proposals").json()["items"][0]
            assert receipt["state"] == "executed" and len(receipt["receipt"]["resources"]) == 2
            owner.post(
                f"/workspaces/{wid}/connections/{connection['id']}/revoke", json={"version": 1}
            )
            owner.post(f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 1})
            assert owner.get(f"/workspaces/{wid}/knowledge?kind=external").json()["total"] == 0
            assert owner.get(f"/workspaces/{wid}/sources/document/{source_id}").status_code == 404
            assert (
                owner.get(f"/workspaces/{wid}/answers").json()["items"][0]["state"]
                == "evidence_unavailable"
            )
            # Exercise the new schema and transport boundaries on real PostgreSQL,
            # with synthetic PDF bytes and an explicit private-provider fixture.
            from dataclasses import replace
            from unittest.mock import patch

            from test_pdf import pdf_bytes
            from test_private_github import authorize, configure, transport

            from rate_limit import SharedRateLimiter
            from semantic import index_once

            configure(app)
            app.state.settings = replace(app.state.settings, local_index_enabled=True)
            pdf = owner.post(
                f"/workspaces/{wid}/documents",
                json={
                    "filename": "pilot.pdf",
                    "title": "PDF pilot",
                    "content_base64": base64.b64encode(pdf_bytes()).decode(),
                },
            )
            assert pdf.status_code == 202, pdf.text
            assert ingest_once(app.state.session_factory)
            passages = owner.get(f"/workspaces/{wid}/knowledge?kind=document&q=page").json()[
                "items"
            ]
            assert {
                owner.get(f"/workspaces/{wid}/sources/document/{p['id']}").json()["page_number"]
                for p in passages
            } == {1, 2}
            assert owner.post(f"/workspaces/{wid}/retrieval-index").status_code == 202
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _: index_once(app.state.session_factory), range(2)))
            assert (
                owner.get(
                    f"/workspaces/{wid}/knowledge?kind=document&q=revocable&ranking=hybrid"
                ).json()["index_status"]
                == "ready"
            )
            with patch("github_app.request_json", transport):
                private = authorize(owner, wid, app)["connection"]
                assert sync_once(app.state.session_factory, settings=app.state.settings)
                assert (
                    owner.get(f"/workspaces/{wid}/knowledge?kind=external&q=authentication").json()[
                        "total"
                    ]
                    == 1
                )
                assert (
                    owner.post(
                        f"/workspaces/{wid}/connections/{private['id']}/revoke", json={"version": 1}
                    ).status_code
                    == 200
                )
                assert owner.get(f"/workspaces/{wid}/knowledge?kind=external").json()["total"] == 0
            limits = [
                SharedRateLimiter(app.state.session_factory, "test-only-postgres-quota", limit=3)
                for _ in range(2)
            ]
            from fastapi import HTTPException

            def count_attempt(n):
                try:
                    limits[n % 2].check("synthetic-peer")
                    return 1
                except HTTPException as error:
                    assert error.status_code == 429
                    return 0

            with ThreadPoolExecutor(max_workers=4) as pool:
                assert sum(pool.map(count_attempt, range(8))) == 3
        print(
            "PostgreSQL sources, PDF pages, private authorization, hybrid indexing, shared quotas and competing native action workers passed"
        )
    finally:
        with service.begin() as db:
            db.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        service.dispose()


if __name__ == "__main__":
    main()
