"""Frozen author-curated connected-source evaluation and local latency sample.

These queries were held out from the original 11-query tuning fixture. They are
not independently human-judged. All data is synthetic; provider I/O is a fixture.
The live GitHub adapter is verified separately. No model or network calls occur.
"""

import argparse
import base64
import json
import statistics
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def evaluate():
    from fastapi.testclient import TestClient

    from config import Settings
    from documents import ingest_once
    from main import create_app
    from migrate import upgrade_database
    from models import DocumentPassage, DocumentRevision, ImportedRecord, Message
    from repositories import sync_once

    with TemporaryDirectory(prefix="parallel-connected-evaluation-") as directory:
        url = f"sqlite:///{directory}/evaluation.db"
        upgrade_database(url)
        app = create_app(
            Settings(
                database_url=url,
                secret_key="test-only-connected-evaluation-key-32-bytes",
                environment="test",
                github_connector_enabled=True,
            )
        )
        factory = app.state.session_factory
        with TestClient(app) as owner, TestClient(app) as outsider:
            for client, name in [(owner, "Owner"), (outsider, "Other")]:
                response = client.post(
                    "/auth/register",
                    json={
                        "name": name,
                        "email": f"{name}@example.test",
                        "password": "evaluation-password",
                    },
                )
                assert response.status_code == 201
            user_id = owner.get("/me").json()["id"]
            wid = owner.post("/workspaces", json={"name": "Connected synthetic evaluation"}).json()[
                "id"
            ]
            records = {}

            def document(name, title, text):
                response = owner.post(
                    f"/workspaces/{wid}/documents",
                    json={
                        "title": title,
                        "filename": name + ".md",
                        "content_base64": base64.b64encode(text.encode()).decode(),
                    },
                )
                assert response.status_code == 202, response.text
                item = response.json()
                ingest_once(factory)
                with factory() as db:
                    revision = (
                        db.query(DocumentRevision)
                        .filter_by(document_id=item["id"], version=1)
                        .one()
                    )
                    records[name] = (
                        db.query(DocumentPassage).filter_by(revision_id=revision.id).one().id
                    )
                return item

            launch = document(
                "launch_doc",
                "Harbor launch checklist",
                "Harbor launch requires approval from privacy reviewers. Refresh sessions after credentials change.",
            )
            document(
                "retry_doc",
                "Harbor retry policy",
                "Harbor retry policy: use exponential backoff and jitter. Never retry non-idempotent mutations automatically.",
            )
            document(
                "cache_doc",
                "Cedar cache policy",
                "Cedar cache policy: do not cache personalized pages. Cache public assets.",
            )
            budget = document(
                "old_budget_doc", "Deployment budget", "Deployment legacybudget is twelve."
            )
            response = owner.post(
                f"/workspaces/{wid}/documents/{budget['id']}/revisions",
                json={
                    "version": 1,
                    "title": "Deployment budget",
                    "filename": "budget.md",
                    "content_base64": base64.b64encode(
                        b"Deployment currentbudget is twenty."
                    ).decode(),
                },
            )
            assert response.status_code == 202
            ingest_once(factory)
            for name, title in [("launch_task", "Harbor launch"), ("retry_task", "Harbor retry")]:
                response = owner.post(f"/workspaces/{wid}/tasks", json={"title": title})
                assert response.status_code == 201
                records[name] = response.json()["id"]
            session = owner.post(
                f"/workspaces/{wid}/decisions",
                json={
                    "title": "Session policy",
                    "statement": "Revocable sessions invalidate copied tokens after logout.",
                    "status": "accepted",
                },
            ).json()
            records["session_decision"] = session["id"]
            storage = owner.post(
                f"/workspaces/{wid}/decisions",
                json={"title": "Storage policy", "statement": "Use SQLite"},
            ).json()
            records["storage_revision"] = storage["id"] + "@1"
            fields = {
                key: storage[key]
                for key in [
                    "title",
                    "context",
                    "statement",
                    "rationale",
                    "alternatives",
                    "tradeoffs",
                    "status",
                    "version",
                ]
            }
            response = owner.patch(
                f"/workspaces/{wid}/decisions/{storage['id']}",
                json={
                    **fields,
                    "statement": "Use PostgreSQL",
                    "status": "accepted",
                    "reason": "Concurrent write requirements",
                },
            )
            assert response.status_code == 200
            connection = owner.post(
                f"/workspaces/{wid}/connections", json={"repository": "synthetic/harbor"}
            ).json()

            def fixture_fetch(_repo):
                return [
                    {
                        "provider_id": "issues:1",
                        "record_type": "issues",
                        "title": "Harbor retry incident",
                        "body": "Use exponential backoff and jitter.",
                        "original_url": "https://github.com/synthetic/harbor/issues/1",
                        "status": "open",
                    }
                ]

            sync_once(factory, fixture_fetch)
            with factory() as db:
                records["retry_issue"] = (
                    db.query(ImportedRecord).filter_by(connection_id=connection["id"]).one().id
                )
                for index in range(200):
                    db.add(
                        Message(
                            id=str(uuid4()),
                            workspace_id=wid,
                            user_id=user_id,
                            sender_id=user_id,
                            sender_name="Owner",
                            role="user",
                            content=f"Unrelated daily check-in {index}",
                        )
                    )
                db.commit()
            queries = json.loads(Path(__file__).with_name("connected_queries.json").read_text())
            reports = {}
            for ranking in ["legacy", "coverage"]:
                cases, timings, citation_count = [], [], 0
                for query in queries:
                    params = {
                        key: value
                        for key, value in query.items()
                        if key not in {"name", "expected"}
                    }
                    params.update(ranking=ranking, limit=5)
                    result = None
                    for _ in range(10):
                        started = time.perf_counter()
                        response = owner.get(f"/workspaces/{wid}/knowledge", params=params)
                        timings.append((time.perf_counter() - started) * 1000)
                        assert response.status_code == 200, response.text
                        result = response.json()
                    ids = [item["id"] for item in result["items"]]
                    expected = {records[name] for name in query["expected"]}
                    hits = len(set(ids) & expected)
                    for item in result["items"]:
                        source = owner.get(f"/workspaces/{wid}/sources/{item['kind']}/{item['id']}")
                        assert source.status_code == 200 and source.json()["id"] == item["id"]
                        citation_count += 1
                    cases.append(
                        {
                            "name": query["name"],
                            "precision_at_5": hits / len(ids) if ids else float(not expected),
                            "recall_at_5": hits / len(expected) if expected else float(not ids),
                            "reciprocal_rank": next(
                                (1 / (i + 1) for i, item in enumerate(ids) if item in expected), 0
                            )
                            if expected
                            else None,
                            "returned": len(ids),
                            "relevant": len(expected),
                        }
                    )
                ranks = [
                    case["reciprocal_rank"] for case in cases if case["reciprocal_rank"] is not None
                ]
                reports[ranking] = {
                    "query_count": len(cases),
                    "macro_precision_at_5": statistics.mean(c["precision_at_5"] for c in cases),
                    "macro_recall_at_5": statistics.mean(c["recall_at_5"] for c in cases),
                    "mean_reciprocal_rank": statistics.mean(ranks),
                    "citation_correctness": 1.0,
                    "citations_checked": citation_count,
                    "latency_samples": len(timings),
                    "latency_p50_ms": statistics.median(timings),
                    "latency_p95_ms": sorted(timings)[int(len(timings) * 0.95) - 1],
                    "scenarios": cases,
                }
            before = owner.post(
                f"/workspaces/{wid}/answers",
                json={
                    "question": "privacy reviewers",
                    "idempotency_key": "evaluation-question-0001",
                },
            ).json()
            assert before["state"] == "completed"
            owner.post(f"/workspaces/{wid}/documents/{launch['id']}/archive", json={"version": 1})
            owner.post(
                f"/workspaces/{wid}/connections/{connection['id']}/revoke", json={"version": 1}
            )
            checks = [
                owner.get(f"/workspaces/{wid}/sources/document/{records['launch_doc']}").status_code
                == 404,
                owner.get(
                    f"/workspaces/{wid}/sources/external/{records['retry_issue']}"
                ).status_code
                == 404,
                owner.get(f"/workspaces/{wid}/answers").json()["items"][0]["state"]
                == "evidence_unavailable",
                outsider.get(f"/workspaces/{wid}/knowledge").status_code == 404,
                outsider.get(f"/workspaces/{wid}/documents").status_code == 404,
                outsider.get(f"/workspaces/{wid}/answers").status_code == 404,
            ]
            assert all(checks)
            assert (
                reports["coverage"]["macro_recall_at_5"] >= reports["legacy"]["macro_recall_at_5"]
            )
            assert (
                reports["coverage"]["macro_precision_at_5"]
                >= reports["legacy"]["macro_precision_at_5"]
            )
            return {
                "fixture": "connected-synthetic-v1",
                "judgments": "Frozen author-curated labels; held out from original 11-query fixture, not independently human-adjudicated",
                "workload": "SQLite; 200 unrelated messages, four documents/five revisions, two tasks, two decisions/three revisions, one imported issue; 10 sequential requests per query per ranking, includes API/session overhead",
                "rankings": reports,
                "safety_checks_passed": sum(checks),
                "safety_checks_total": len(checks),
                "unauthorized_retrieval_count": 0,
                "limitations": "Synthetic workload; no semantic embeddings, multilingual normalization or model quality evaluation. Latency is local, not a production capacity claim.",
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(evaluate(), indent=2)
    if args.output:
        args.output.write_text(report + "\n")
    print(report)


if __name__ == "__main__":
    main()
