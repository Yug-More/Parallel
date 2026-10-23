"""Irreversible operations run only against pytest's disposable databases."""

from test_collaboration import join, project, task
from test_documents import upload
from test_intelligence import drain, start
from test_native_actions import approve, proposal

from actions import execute_once
from documents import ingest_once
from models import AgentRun, DocumentPassage, DocumentRevision, Message, RetentionReceipt, Task


def preview(client, wid, **scope):
    response = client.post(
        f"/workspaces/{wid}/retention/preview", json=scope or {"scope": "derived"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def execute(client, wid, plan, **changes):
    payload = {
        key: plan[key]
        for key in ["scope", "target_id", "expected_revision", "expires", "plan_hash"]
    }
    return client.post(
        f"/workspaces/{wid}/retention/execute",
        json={**payload, "confirmation": "ERASE REVIEWED CONTENT", **changes},
    )


def test_exact_retention_preview_owner_tamper_staleness_and_replay(accounts, application):
    owner, _ = accounts()
    member, _ = accounts("member@example.test", "Member")
    stranger, _ = accounts("other@example.test", "Other")
    wid = project(owner)
    join(owner, member, wid, "member@example.test")
    url = f"/workspaces/{wid}/retention/preview"
    assert member.post(url, json={"scope": "derived"}).status_code == 403
    assert stranger.post(url, json={"scope": "derived"}).status_code == 404
    plan = preview(owner, wid)
    assert execute(owner, wid, plan, scope="close").status_code == 409
    task(owner, wid, title="Native edit invalidates review")
    assert execute(owner, wid, plan).status_code == 409
    plan = preview(owner, wid)
    assert execute(owner, wid, plan).status_code == 200
    assert execute(owner, wid, plan).status_code == 409
    assert len(owner.get(f"/workspaces/{wid}/retention/receipts").json()["items"]) == 1


def test_document_erasure_cancels_derived_but_preserves_native_tasks_and_receipts(
    accounts, application
):
    owner, _ = accounts()
    wid = project(owner)
    document = upload(owner, wid, b"Sensitive document body").json()
    ingest_once(application.state.session_factory)
    owner.post(f"/workspaces/{wid}/messages", json={"content": "Human-authored history stays"})
    start(owner, wid, agent_type="local.plan.v1", objective="Review evidence; Verify result")
    drain(application)
    item = proposal(owner, wid)
    assert approve(owner, wid, item).status_code == 200
    execute_once(application.state.session_factory)
    original_receipt = proposal(owner, wid)["receipt"]
    plan = preview(owner, wid, scope="document", target_id=document["id"])
    assert execute(owner, wid, plan).status_code == 200
    with application.state.session_factory() as db:
        assert all(row.body == "" for row in db.query(DocumentPassage))
        assert all(
            row.raw_content is None and row.state == "cancelled"
            for row in db.query(DocumentRevision)
        )
        assert all(
            row.outcome is None and row.context == {"knowledge_epoch": -1}
            for row in db.query(AgentRun)
        )
        assert db.query(Task).count() == 2
        assert db.query(Message).filter_by(content="Human-authored history stays").count() == 1
        assert db.query(RetentionReceipt).count() == 1
    assert proposal(owner, wid)["receipt"] == original_receipt
    assert not owner.get(f"/workspaces/{wid}/knowledge?q=Sensitive&kind=document").json()["items"]
    assert not ingest_once(application.state.session_factory)


def test_workspace_closure_denies_reads_and_jobs_but_keeps_owner_audit(accounts, application):
    owner, _ = accounts()
    other, _ = accounts("other@example.test", "Other")
    wid = project(owner)
    upload(owner, wid)
    start(owner, wid)
    plan = preview(owner, wid, scope="close")
    assert execute(owner, wid, plan).status_code == 200
    assert owner.get(f"/workspaces/{wid}").status_code == 404
    assert owner.get(f"/workspaces/{wid}/knowledge?q=secret").status_code == 404
    assert wid not in [row["id"] for row in owner.get("/workspaces").json()]
    assert owner.get(f"/workspaces/{wid}/retention/receipts").status_code == 200
    assert other.get(f"/workspaces/{wid}/retention/receipts").status_code == 404
    assert not ingest_once(application.state.session_factory)
    from orchestration import run_once

    assert not run_once(application.state.session_factory)


def test_retention_discards_answer_finishing_after_erasure(accounts, application, monkeypatch):
    from dataclasses import replace

    import providers

    owner, _ = accounts()
    wid = project(owner)
    upload(owner, wid)
    ingest_once(application.state.session_factory)
    application.state.settings = replace(
        application.state.settings, grounded_model_enabled=True, openai_api_key="fixture-only"
    )

    def late(_settings, _question, evidence):
        plan = preview(owner, wid)
        assert execute(owner, wid, plan).status_code == 200
        return {
            "claims": [
                {
                    "text": "Must not return after erasure",
                    "kind": "fact",
                    "citations": [evidence[0]["ref"]],
                }
            ]
        }

    monkeypatch.setattr(providers, "generate_grounded", late)
    result = owner.post(
        f"/workspaces/{wid}/answers",
        json={
            "question": "revocable sessions",
            "mode": "model",
            "idempotency_key": "late-retention-answer",
        },
    )
    assert result.status_code == 201, result.text
    assert result.json()["state"] == "failed" and result.json()["claims"] == []
