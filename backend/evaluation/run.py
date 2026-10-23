"""Reproducible synthetic API retrieval evaluation. Creates only a temporary DB.

Run from the repository root: python backend/evaluation/run.py [--output path]
No model calls, embeddings or external services. Quality gates are fixture-specific.
"""

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def evaluate():
    from fastapi.testclient import TestClient

    from config import Settings
    from main import create_app
    from migrate import upgrade_database
    from models import Message

    with TemporaryDirectory(prefix="parallel-retrieval-eval-") as directory:
        url = f"sqlite:///{directory}/evaluation.db"
        upgrade_database(url)
        app = create_app(
            Settings(
                database_url=url,
                secret_key="test-only-evaluation-signing-key-32-bytes",
                environment="test",
            )
        )
        with TestClient(app) as owner, TestClient(app) as outsider, TestClient(app) as teammate:

            def register(client, name):
                response = client.post(
                    "/auth/register",
                    json={
                        "name": name,
                        "email": f"{name}@example.test",
                        "password": "evaluation-password",
                    },
                )
                assert response.status_code == 201, response.text
                return response.json()["id"]

            owner_id = register(owner, "Owner")
            register(outsider, "Other")
            teammate_id = register(teammate, "Teammate")
            wid = owner.post("/workspaces", json={"name": "Synthetic retrieval evaluation"}).json()[
                "id"
            ]
            other = outsider.post("/workspaces", json={"name": "Private project"}).json()["id"]
            outsider.post(
                f"/workspaces/{other}/decisions",
                json={
                    "title": "Authentication private",
                    "statement": "Must not leak",
                    "status": "accepted",
                },
            )
            invite = owner.post(
                f"/workspaces/{wid}/invitations", json={"email": "Teammate@example.test"}
            ).json()
            assert teammate.post(f"/invitations/{invite['id']}/accept").status_code == 200
            records = {}

            def create(name, resource, payload):
                response = owner.post(f"/workspaces/{wid}/{resource}", json=payload)
                assert response.status_code == 201, response.text
                records[name] = response.json()["id"]

            create(
                "old_auth",
                "decisions",
                {
                    "title": "Authentication v1",
                    "statement": "Stateless tokens",
                    "status": "accepted",
                },
            )
            create(
                "current_auth",
                "decisions",
                {
                    "title": "Authentication v2",
                    "statement": "Revocable sessions",
                    "status": "accepted",
                },
            )
            assert (
                owner.post(
                    f"/workspaces/{wid}/decisions/{records['old_auth']}/supersede",
                    json={
                        "version": 1,
                        "successor_id": records["current_auth"],
                        "successor_version": 1,
                        "reason": "Copied tokens require revocation",
                    },
                ).status_code
                == 200
            )
            create(
                "release_api", "tasks", {"title": "Release backend API", "status": "in_progress"}
            )
            create("archived", "tasks", {"title": "Obsolete release checklist"})
            owner.post(
                f"/workspaces/{wid}/tasks/{records['archived']}/archive", json={"version": 1}
            )
            marker = owner.get(f"/workspaces/{wid}/continuity").json()["generated_at"]
            create("release_ui", "tasks", {"title": "Release frontend UI"})
            create("cache_yes", "messages", {"content": "Cache policy: cache every response."})
            create(
                "cache_no", "messages", {"content": "Cache policy: never cache private responses."}
            )
            with app.state.session_factory() as db:
                for i in range(240):
                    db.add(
                        Message(
                            id=str(uuid4()),
                            workspace_id=wid,
                            user_id=owner_id,
                            sender_id=owner_id,
                            sender_name="Owner",
                            role="user",
                            content=f"Routine planning entry {i}",
                        )
                    )
                db.commit()
            create(
                "needle",
                "messages",
                {"content": "Zebra migration receipt confirms schema adoption."},
            )
            queries = json.loads(Path(__file__).with_name("queries.json").read_text())
            metrics = []
            citations = correct_citations = 0
            state_checks = state_correct = 0
            for case in queries:
                params = {
                    key: value
                    for key, value in case.items()
                    if key not in {"name", "expected", "since_marker"}
                }
                params["limit"] = 5
                if case.get("since_marker"):
                    params["since"] = marker
                response = owner.get(f"/workspaces/{wid}/knowledge", params=params)
                assert response.status_code == 200, response.text
                result = response.json()
                repeat = owner.get(f"/workspaces/{wid}/knowledge", params=params).json()
                assert result["items"] == repeat["items"], (
                    "Repeated retrieval changed without writes"
                )
                ids = [row["id"] for row in result["items"]]
                relevant = {records[key] for key in case["expected"]}
                hits = len(set(ids) & relevant)
                precision = hits / len(ids) if ids else float(not relevant)
                recall = hits / len(relevant) if relevant else float(not ids)
                rank = (
                    next((1 / (i + 1) for i, item in enumerate(ids) if item in relevant), 0)
                    if relevant
                    else None
                )
                for row in result["items"]:
                    citations += 1
                    source = owner.get(f"/workspaces/{wid}/sources/{row['kind']}/{row['id']}")
                    correct_citations += int(
                        source.status_code == 200
                        and source.json()["id"] == row["id"]
                        and source.json()["version"] == row["version"]
                        and source.json()["workspace_id"] == wid
                    )
                    if not case.get("include_historical") and row["kind"] == "decision":
                        state_checks += 1
                        state_correct += int(row["status"] in {"proposed", "accepted"})
                    if not case.get("include_archived") and row["kind"] == "task":
                        state_checks += 1
                        state_correct += int(not row["archived"])
                metrics.append(
                    {
                        "scenario": case["name"],
                        "precision_at_5": precision,
                        "recall_at_5": recall,
                        "reciprocal_rank": rank,
                        "returned": len(ids),
                        "relevant": len(relevant),
                    }
                )
            assert owner.delete(f"/workspaces/{wid}/members/{teammate_id}").status_code == 200
            unauthorized = denied = 0
            for actor in [outsider, teammate]:
                for endpoint in [
                    "knowledge?q=authentication",
                    "continuity",
                    f"sources/decision/{records['current_auth']}",
                ]:
                    response = actor.get(f"/workspaces/{wid}/{endpoint}")
                    denied += int(response.status_code == 404)
                    unauthorized += int(response.status_code == 200)
            ranks = [
                row["reciprocal_rank"] for row in metrics if row["reciprocal_rank"] is not None
            ]
            report = {
                "method": "deterministic_lexical_v1",
                "fixture": "synthetic-v1",
                "query_count": len(metrics),
                "macro_precision_at_5": sum(row["precision_at_5"] for row in metrics)
                / len(metrics),
                "macro_recall_at_5": sum(row["recall_at_5"] for row in metrics) / len(metrics),
                "mean_reciprocal_rank": sum(ranks) / len(ranks),
                "citation_correctness": correct_citations / citations,
                "citations_checked": citations,
                "current_state_correctness": state_correct / state_checks,
                "current_state_checks": state_checks,
                "unauthorized_retrieval_count": unauthorized,
                "access_denials_checked": denied,
                "scenarios": metrics,
            }
            assert report["macro_recall_at_5"] >= 0.9 and report["macro_precision_at_5"] >= 0.85
            assert report["citation_correctness"] == 1 and report["current_state_correctness"] == 1
            assert unauthorized == 0 and denied == 6
            return report


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
