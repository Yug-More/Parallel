from concurrent.futures import ThreadPoolExecutor

from test_collaboration import join, project, task
from test_documents import upload
from test_intelligence import detail, drain, start

from actions import execute_once
from documents import ingest_once
from models import ActionProposal, Message, Task


def proposal(client, wid):
    items = client.get(f"/workspaces/{wid}/action-proposals").json()["items"]
    assert len(items) == 1
    return items[0]


def approve(client, wid, item, **changes):
    return client.post(
        f"/workspaces/{wid}/action-proposals/{item['id']}/approve",
        json={
            "payload_hash": item["payload_hash"],
            **changes,
        },
    )


def test_coordinator_exact_plan_and_atomic_receipt(accounts, application):
    owner, _ = accounts()
    member, _ = accounts("bob@example.test", "Bob")
    wid = project(owner)
    join(owner, member, wid)
    task(owner, wid, title="Existing work")
    run = start(
        member,
        wid,
        agent_type="local.delivery.v1",
        objective="Existing work; Review sessions; Verify logout",
    )
    drain(application)
    result = detail(owner, wid, run)
    assert result["state"] == "completed", result
    assert len(result["children"]) == 2
    item = proposal(owner, wid)
    assert [t["title"] for t in item["payload"]["proposal"]["tasks"]] == [
        "Review sessions",
        "Verify logout",
    ]
    assert approve(member, wid, item).status_code == 403
    assert approve(owner, wid, item, payload_hash="0" * 64).status_code == 409
    assert approve(owner, wid, item).status_code == 200
    assert approve(owner, wid, item).status_code == 409
    factory = application.state.session_factory
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: execute_once(factory), range(2)))
    receipt = proposal(owner, wid)
    assert receipt["state"] == "executed" and len(receipt["receipt"]["resources"]) == 2
    assert not execute_once(factory)
    tasks = owner.get(f"/workspaces/{wid}/tasks").json()["items"]
    assert len(tasks) == 3
    assert all(t["status"] == "todo" and t["assignee_id"] is None for t in tasks)
    second = next(t for t in tasks if t["title"] == "Verify logout")
    assert len(second["dependencies"]) == 1


def test_native_execution_fails_closed_on_context_change_and_tamper(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    start(owner, wid, agent_type="local.plan.v1", objective="Review design; Test implementation")
    drain(application)
    item = proposal(owner, wid)
    approve(owner, wid, item)
    task(owner, wid, title="New context")
    assert execute_once(application.state.session_factory)
    failed = proposal(owner, wid)
    assert failed["state"] == "failed" and failed["error_code"] == "context_changed"
    with application.state.session_factory() as db:
        assert db.query(Task).filter_by(workspace_id=wid).count() == 1
        action = db.query(ActionProposal).one()
        action.state, action.error_code = "approved", None
        action.payload = {**action.payload, "proposal": {"action": "create_task_plan", "tasks": []}}
        db.commit()
    assert execute_once(application.state.session_factory)
    assert proposal(owner, wid)["state"] == "failed"


def test_research_and_published_reports_are_hidden_after_document_revocation(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    doc = upload(owner, wid).json()
    ingest_once(application.state.session_factory)
    run = start(
        owner, wid, agent_type="local.research.v1", objective="revocable sessions", publish=True
    )
    drain(application)
    report = detail(owner, wid, run)
    assert report["state"] == "waiting_for_approval", report
    assert any(s["kind"] == "document" for f in report["outcome"]["facts"] for s in f["sources"])
    approval = report["approval"]
    assert (
        owner.post(
            f"/workspaces/{wid}/approvals/{approval['id']}/approve",
            json={"payload_hash": approval["payload_hash"]},
        ).status_code
        == 200
    )
    drain(application)
    assert detail(owner, wid, run)["state"] == "completed"
    with application.state.session_factory() as db:
        assert db.query(Message).filter_by(workspace_id=wid).one().knowledge_epoch is not None
    owner.post(f"/workspaces/{wid}/documents/{doc['id']}/archive", json={"version": 1})
    hidden = detail(owner, wid, run)
    assert hidden["outcome"] is None and hidden["context"] is None
    assert hidden["approval"]["payload"] is None
    messages = owner.get(f"/workspaces/{wid}/messages").json()
    assert "Report hidden" in messages[0]["content"]
    assert owner.get(f"/workspaces/{wid}/knowledge?q=revocable&kind=message").json()["total"] == 0


def test_removed_initiator_cannot_execute_native_plan(accounts, application):
    owner, _ = accounts()
    member, member_data = accounts("bob@example.test", "Bob")
    wid = project(owner)
    join(owner, member, wid)
    start(member, wid, agent_type="local.plan.v1", objective="Review design")
    drain(application)
    item = proposal(owner, wid)
    approve(owner, wid, item)
    members = owner.get(f"/workspaces/{wid}/members").json()
    member_id = next(m["id"] for m in members if m["name"] == "Bob")
    assert owner.delete(f"/workspaces/{wid}/members/{member_id}").status_code == 200
    execute_once(application.state.session_factory)
    assert proposal(owner, wid)["error_code"] == "initiator_removed"
    assert owner.get(f"/workspaces/{wid}/tasks").json()["total"] == 0


def test_payload_tamper_is_rejected_without_partial_tasks(accounts, application):
    from orchestration import digest

    owner, _ = accounts()
    wid = project(owner)
    start(owner, wid, agent_type="local.plan.v1", objective="Review design; Test code")
    drain(application)
    item = proposal(owner, wid)
    approve(owner, wid, item)
    with application.state.session_factory() as db:
        action = db.query(ActionProposal).one()
        action.payload = {
            **action.payload,
            "proposal": {**action.payload["proposal"], "tasks": [{"title": "Tampered"}]},
        }
        action.payload_hash = digest(action.payload)
        db.commit()
    execute_once(application.state.session_factory)
    failed = proposal(owner, wid)
    assert failed["state"] == "failed" and failed["error_code"] == "proposal_payload_mismatch"
    assert owner.get(f"/workspaces/{wid}/tasks").json()["total"] == 0


def test_native_expiry_and_rejection_execute_no_resources(accounts, application):
    from datetime import timedelta

    from models import utc_now

    owner, _ = accounts()
    wid = project(owner)
    start(owner, wid, agent_type="local.plan.v1", objective="Review design")
    drain(application)
    item = proposal(owner, wid)
    with application.state.session_factory() as db:
        action = db.query(ActionProposal).one()
        action.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert approve(owner, wid, item).status_code == 409
    assert execute_once(application.state.session_factory)
    assert proposal(owner, wid)["state"] == "expired"
    assert owner.get(f"/workspaces/{wid}/tasks").json()["total"] == 0


def test_owner_transfer_after_native_approval_fails_closed(accounts, application):
    owner, _ = accounts()
    member, profile = accounts("bob@example.test", "Bob")
    wid = project(owner)
    join(owner, member, wid)
    start(owner, wid, agent_type="local.plan.v1", objective="Review design")
    drain(application)
    item = proposal(owner, wid)
    approve(owner, wid, item)
    response = owner.post(f"/workspaces/{wid}/transfer-ownership", json={"user_id": profile["id"]})
    assert response.status_code == 200, response.text
    execute_once(application.state.session_factory)
    assert proposal(member, wid)["error_code"] == "approver_no_longer_owner"
    assert member.get(f"/workspaces/{wid}/tasks").json()["total"] == 0


def test_planner_preserves_numbers_and_deduplicates_titles(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    start(
        owner, wid, agent_type="local.plan.v1", objective="2026 launch; Verify v2.0; Review; review"
    )
    drain(application)
    titles = [item["title"] for item in proposal(owner, wid)["payload"]["proposal"]["tasks"]]
    assert titles == ["2026 launch", "Verify v2.0", "Review"]


def test_phase3_pending_publication_context_remains_compatible(accounts, application):
    from models import AgentRun

    owner, _ = accounts()
    wid = project(owner)
    task(owner, wid, title="Existing Phase 3 work")
    run = start(owner, wid, publish=True)
    drain(application)
    result = detail(owner, wid, run)
    with application.state.session_factory() as db:
        old = db.get(AgentRun, run["id"])
        # Phase 3 persisted these native fields; its hash format must remain valid.
        old.context = {
            key: value
            for key, value in old.context.items()
            if key not in {"knowledge_epoch", "knowledge_sources", "objective"}
        }
        db.commit()
    approval = result["approval"]
    response = owner.post(
        f"/workspaces/{wid}/approvals/{approval['id']}/approve",
        json={"payload_hash": approval["payload_hash"]},
    )
    assert response.status_code == 200
    drain(application)
    assert detail(owner, wid, run)["state"] == "completed"


def test_plan_uses_blockers_decisions_and_distinguishes_historical_evidence(accounts, application):
    import base64

    from test_intelligence import decision

    owner, _ = accounts()
    wid = project(owner)
    prerequisite = task(owner, wid, title="Session review")
    task(owner, wid, title="Session release", dependency_ids=[prerequisite["id"]])
    choice = decision(
        owner,
        wid,
        title="Session architecture",
        statement="Use revocable sessions",
        status="accepted",
    )
    doc = upload(owner, wid).json()
    ingest_once(application.state.session_factory)
    response = owner.post(
        f"/workspaces/{wid}/documents/{doc['id']}/revisions",
        json={
            "filename": "session-v2.md",
            "title": "Architecture notes",
            "version": 1,
            "content_base64": base64.b64encode(
                b"Revocable sessions now require rotating credentials."
            ).decode(),
        },
    )
    assert response.status_code == 202
    ingest_once(application.state.session_factory)
    run = start(owner, wid, agent_type="local.delivery.v1", objective="Review revocable sessions")
    drain(application)
    result = detail(owner, wid, run)
    assert result["state"] == "completed", result
    assert "existing blocked task" in result["outcome"]["summary"]
    assert any("historical" in fact["text"] for fact in result["outcome"]["facts"])
    refs = proposal(owner, wid)["payload"]["proposal"]["evidence"]
    assert any(ref["id"] == choice["id"] and ref["kind"] == "decision" for ref in refs)
    assert {ref["version"] for ref in refs if ref["kind"] == "document"} == {1, 2}
