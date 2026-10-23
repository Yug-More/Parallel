from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from test_collaboration import join, project, task

from models import AgentRun, Approval, DecisionRevision, Task, utc_now
from orchestration import run_once


def decision(client, wid, **changes):
    response = client.post(
        f"/workspaces/{wid}/decisions",
        json={
            "title": "Authentication architecture",
            "statement": "Use revocable sessions",
            **changes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def edit(item, **changes):
    fields = [
        "title",
        "context",
        "statement",
        "rationale",
        "alternatives",
        "tradeoffs",
        "status",
        "version",
    ]
    return {
        **{key: item[key] for key in fields},
        "sources": [{"kind": s["cited"]["kind"], "id": s["cited"]["id"]} for s in item["sources"]],
        "reason": "Correct the record",
        **changes,
    }


def start(client, wid, **changes):
    response = client.post(
        f"/workspaces/{wid}/runs",
        json={
            "agent_type": "local.status.v1",
            "objective": "Prepare handoff",
            "idempotency_key": "request-key-0001",
            **changes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def drain(application):
    for _ in range(30):
        if not run_once(application.state.session_factory):
            return
    raise AssertionError("Worker did not become idle")


def detail(client, wid, run):
    return client.get(f"/workspaces/{wid}/runs/{run['id']}").json()


def test_decision_revision_sources_and_noop(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    t = task(owner, wid, title="Evidence task")
    message = owner.post(
        f"/workspaces/{wid}/messages", json={"content": "Session tokens need revocation"}
    ).json()
    d = decision(
        owner,
        wid,
        sources=[{"kind": "task", "id": t["id"]}, {"kind": "message", "id": message["id"]}],
    )
    assert len(d["sources"]) == 2
    response = owner.patch(
        f"/workspaces/{wid}/decisions/{d['id']}",
        json=edit(d, status="accepted", rationale="Copied tokens must stop working"),
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["version"] == 2
    assert owner.patch(f"/workspaces/{wid}/decisions/{d['id']}", json=edit(d)).status_code == 409
    assert (
        owner.patch(f"/workspaces/{wid}/decisions/{d['id']}", json=edit(updated)).json()["version"]
        == 2
    )
    owner.patch(
        f"/workspaces/{wid}/tasks/{t['id']}", json={"version": 1, "title": "Corrected task"}
    )
    current = owner.get(f"/workspaces/{wid}/decisions/{d['id']}").json()
    source = next(s for s in current["sources"] if s["cited"]["kind"] == "task")
    assert source["cited"]["title"] == "Evidence task"
    assert source["current"]["title"] == "Corrected task"
    history = owner.get(f"/workspaces/{wid}/decisions/{d['id']}/history?limit=1").json()
    assert history["total"] == 2 and len(history["items"]) == 1
    with application.state.session_factory() as db:
        assert db.query(DecisionRevision).count() == 2


def test_supersession_history_terminal_and_current_retrieval(accounts):
    owner, _ = accounts()
    wid = project(owner)
    old = decision(
        owner,
        wid,
        title="Stateless authentication",
        statement="Accept stateless JWT",
        status="accepted",
    )
    new = decision(owner, wid, title="Revocable authentication", status="accepted")
    body = {
        "version": 1,
        "successor_id": new["id"],
        "successor_version": 1,
        "reason": "Require server-side revocation",
    }
    assert (
        owner.post(f"/workspaces/{wid}/decisions/{old['id']}/supersede", json=body).json()["status"]
        == "superseded"
    )
    assert (
        owner.post(f"/workspaces/{wid}/decisions/{old['id']}/supersede", json=body).status_code
        == 409
    )
    assert (
        owner.patch(
            f"/workspaces/{wid}/decisions/{old['id']}", json=edit(old, version=2)
        ).status_code
        == 409
    )
    current = owner.get(f"/workspaces/{wid}/knowledge?q=authentication&kind=decision").json()
    assert [row["id"] for row in current["items"]] == [new["id"]]
    historical = owner.get(
        f"/workspaces/{wid}/knowledge?q=authentication&include_historical=true"
    ).json()
    assert old["id"] in {row["id"] for row in historical["items"]}
    versions = owner.get(f"/workspaces/{wid}/decisions/{old['id']}/history").json()["items"]
    assert versions[0]["snapshot"]["superseded_by_id"] == new["id"]
    assert versions[1]["snapshot"]["statement"] == "Accept stateless JWT"


@pytest.mark.parametrize("target", ["task", "message", "decision", "activity"])
def test_cross_workspace_source_linking_is_rejected(accounts, target):
    owner, _ = accounts()
    outsider, _ = accounts("other@example.test")
    wid, other = project(owner), project(outsider)
    if target == "task":
        record = task(outsider, other)
    elif target == "decision":
        record = decision(outsider, other)
    elif target == "message":
        record = outsider.post(f"/workspaces/{other}/messages", json={"content": "Private"}).json()
    else:
        task(outsider, other)
        record = outsider.get(f"/workspaces/{other}/activity").json()[0]
    response = owner.post(
        f"/workspaces/{wid}/decisions",
        json={
            "title": "Invalid",
            "statement": "No leak",
            "sources": [{"kind": target, "id": record["id"]}],
        },
    )
    assert response.status_code == 404
    assert owner.get(f"/workspaces/{wid}/sources/{target}/{record['id']}").status_code == 404
    assert owner.get(f"/workspaces/{other}/knowledge").status_code == 404
    assert owner.get(f"/workspaces/{other}/continuity").status_code == 404


def test_decision_reject_self_links_and_invalid_transition(accounts):
    owner, _ = accounts()
    wid = project(owner)
    d = decision(owner, wid)
    assert (
        owner.patch(
            f"/workspaces/{wid}/decisions/{d['id']}",
            json=edit(d, sources=[{"kind": "decision", "id": d["id"]}]),
        ).status_code
        == 422
    )
    rejected = owner.patch(
        f"/workspaces/{wid}/decisions/{d['id']}", json=edit(d, status="rejected")
    ).json()
    assert rejected["status"] == "rejected"
    assert (
        owner.patch(
            f"/workspaces/{wid}/decisions/{d['id']}", json=edit(rejected, status="accepted")
        ).status_code
        == 409
    )
    accepted = decision(owner, wid, status="accepted")
    assert (
        owner.patch(
            f"/workspaces/{wid}/decisions/{accepted['id']}", json=edit(accepted, status="proposed")
        ).status_code
        == 409
    )


def test_competing_decision_edits(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    d = decision(owner, wid)
    cookies = dict(owner.cookies)

    def save(title):
        with TestClient(application) as browser:
            browser.cookies.update(cookies)
            return browser.patch(
                f"/workspaces/{wid}/decisions/{d['id']}", json=edit(d, title=title)
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, ["First correction", "Second correction"])) == [200, 409]
    assert owner.get(f"/workspaces/{wid}/decisions/{d['id']}/history").json()["total"] == 2


def test_search_ranking_pagination_time_archive_and_missing(accounts):
    owner, _ = accounts()
    wid = project(owner)
    before = owner.get(f"/workspaces/{wid}/continuity").json()["generated_at"]
    best = task(owner, wid, title="Authentication session", description="Revocation")
    task(owner, wid, title="Unrelated", description="authentication session")
    archived = task(owner, wid, title="Authentication session archived")
    owner.post(f"/workspaces/{wid}/tasks/{archived['id']}/archive", json={"version": 1})
    rows = owner.get(
        f"/workspaces/{wid}/knowledge",
        params={"q": "Authentication session", "kind": "task", "limit": 1, "since": before},
    ).json()
    assert rows["items"][0]["id"] == best["id"] and rows["total"] == 2
    second = owner.get(
        f"/workspaces/{wid}/knowledge?q=Authentication+session&kind=task&limit=1&offset=1"
    ).json()
    assert second["items"][0]["id"] != best["id"]
    assert (
        owner.get(
            f"/workspaces/{wid}/knowledge?q=Authentication&kind=task&include_archived=true"
        ).json()["total"]
        == 3
    )
    assert (
        owner.get(f"/workspaces/{wid}/knowledge?q=NoSuchEvidence").json()["evidence"]
        == "no_matching_evidence"
    )
    assert owner.get(f"/workspaces/{wid}/knowledge?since=2026-01-01T00:00:00").status_code == 422
    assert owner.get(f"/workspaces/{wid}/knowledge?limit=101").status_code == 422
    assert owner.get(f"/workspaces/{wid}/knowledge", params={"until": before}).json()["items"] == []


def test_continuity_first_returning_visit_and_supersession(accounts):
    owner, _ = accounts()
    wid = project(owner)
    first = owner.get(f"/workspaces/{wid}/continuity").json()
    assert first["first_visit"] and first["task_counts"] == {}
    assert (
        owner.post(
            f"/workspaces/{wid}/continuity/visit", json={"through": first["generated_at"]}
        ).status_code
        == 200
    )
    old = decision(owner, wid, status="accepted")
    new = decision(owner, wid, title="New decision", status="accepted")
    owner.post(
        f"/workspaces/{wid}/decisions/{old['id']}/supersede",
        json={
            "version": 1,
            "successor_id": new["id"],
            "successor_version": 1,
            "reason": "Changed design",
        },
    )
    task(owner, wid, status="done")
    returned = owner.get(f"/workspaces/{wid}/continuity").json()
    assert not returned["first_visit"] and returned["since"] == first["generated_at"]
    assert returned["decision_counts"] == {"accepted": 1, "superseded": 1}
    assert returned["task_counts"]["done"] == 1
    assert any(row["snapshot"]["status"] == "superseded" for row in returned["decision_changes"])
    future = (utc_now() + timedelta(days=1)).isoformat() + "+00:00"
    assert (
        owner.post(f"/workspaces/{wid}/continuity/visit", json={"through": future}).status_code
        == 422
    )
    owner.post(f"/workspaces/{wid}/continuity/visit", json={"through": returned["generated_at"]})
    assert owner.get(f"/workspaces/{wid}/continuity").json()["event_total"] == 0


def test_real_agents_delegation_sources_and_persistence(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    prerequisite = task(owner, wid, title="Design schema")
    dependent = task(owner, wid, title="Implement endpoint", dependency_ids=[prerequisite["id"]])
    decision(owner, wid, status="accepted")
    run = start(owner, wid, agent_type="local.handoff.v1")
    assert run["state"] == "queued" and run["outcome"] is None
    drain(application)
    saved = detail(owner, wid, run)
    assert saved["state"] == "completed" and len(saved["children"]) == 2
    assert all(row["state"] == "completed" for row in saved["children"])
    assert any(
        dependent["id"] in [s["id"] for s in f["sources"]] for f in saved["outcome"]["facts"]
    )
    assert "1 open tasks have blockers" in saved["outcome"]["summary"]
    assert owner.get(f"/workspaces/{wid}/tasks/{dependent['id']}").json()["status"] == "todo"
    assert {row["event"] for row in saved["events"]} >= {
        "queued",
        "plan_saved",
        "started",
        "completed",
    }
    with application.state.session_factory() as db:
        assert db.get(AgentRun, run["id"]).outcome == saved["outcome"]
    assert not run_once(application.state.session_factory)


def test_idempotency_and_explicit_retry_limit(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    run = start(owner, wid)
    assert start(owner, wid)["id"] == run["id"]
    assert (
        owner.post(
            f"/workspaces/{wid}/runs",
            json={
                "agent_type": "local.status.v1",
                "objective": "Different payload",
                "idempotency_key": "request-key-0001",
            },
        ).status_code
        == 409
    )
    for attempt in range(1, 4):

        def broken(*args):
            raise RuntimeError("private-provider-secret-must-not-leak")

        assert run_once(application.state.session_factory, broken)
        saved = detail(owner, wid, run)
        assert saved["state"] == "failed" and saved["error_code"] == "execution_failed"
        response = owner.post(
            f"/workspaces/{wid}/runs/{run['id']}/retry",
            json={"idempotency_key": f"retry-key-{attempt}"},
        )
        assert response.status_code == (409 if attempt == 3 else 201)
        if attempt < 3:
            replay = owner.post(
                f"/workspaces/{wid}/runs/{run['id']}/retry",
                json={"idempotency_key": f"retry-key-{attempt}"},
            )
            assert replay.json()["id"] == response.json()["id"]
            assert (
                owner.post(
                    f"/workspaces/{wid}/runs/{run['id']}/retry",
                    json={"idempotency_key": "another-retry-key"},
                ).status_code
                == 409
            )
            run = response.json()


def test_task_delegation_blocking_and_changes_before_execution(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    prerequisite = task(owner, wid)
    dependent = task(owner, wid, dependency_ids=[prerequisite["id"]])
    body = {
        "agent_type": "local.status.v1",
        "objective": "Implement",
        "task_id": dependent["id"],
        "idempotency_key": "blocked-key-0001",
    }
    assert owner.post(f"/workspaces/{wid}/runs", json=body).status_code == 409
    analyzer = start(owner, wid, agent_type="local.dependencies.v1", task_id=dependent["id"])
    drain(application)
    assert detail(owner, wid, analyzer)["outcome"]["dependency_chains"]
    ready = start(owner, wid, task_id=prerequisite["id"], idempotency_key="ready-key-0001")
    owner.patch(
        f"/workspaces/{wid}/tasks/{prerequisite['id']}", json={"version": 1, "status": "blocked"}
    )
    drain(application)
    assert detail(owner, wid, ready)["error_code"] == "task_blocked"


@pytest.mark.parametrize("change", ["remove", "cancel", "task"])
def test_inflight_permission_cancellation_and_context_changes(accounts, application, change):
    owner, _ = accounts()
    member, data = accounts("bob@example.test")
    wid = project(owner)
    join(owner, member, wid)
    t = task(owner, wid)
    run = start(member, wid)
    from orchestration import compute

    def during(contract, context, children):
        if change == "remove":
            assert owner.delete(f"/workspaces/{wid}/members/{data['id']}").status_code == 200
        elif change == "cancel":
            assert owner.post(f"/workspaces/{wid}/runs/{run['id']}/cancel").status_code == 200
        else:
            assert (
                owner.patch(
                    f"/workspaces/{wid}/tasks/{t['id']}", json={"version": 1, "title": "Changed"}
                ).status_code
                == 200
            )
        return compute(contract, context, children)

    assert run_once(application.state.session_factory, during)
    saved = detail(owner, wid, run)
    assert saved["state"] == ("cancelled" if change == "cancel" else "failed")
    assert saved["outcome"] is None
    if change == "remove":
        assert member.get(f"/workspaces/{wid}/runs/{run['id']}").status_code == 404
        assert member.get(f"/workspaces/{wid}/knowledge").status_code == 404


def test_stale_run_recovery_and_parent_cancellation(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    run = start(owner, wid)
    with application.state.session_factory() as db:
        row = db.get(AgentRun, run["id"])
        row.state, row.lease_token, row.lease_until = (
            "running",
            "crashed-worker",
            utc_now() - timedelta(seconds=1),
        )
        db.commit()
    drain(application)
    assert detail(owner, wid, run)["error_code"] == "lease_expired"
    parent = start(owner, wid, agent_type="local.handoff.v1", idempotency_key="coordinator-0001")
    assert owner.post(f"/workspaces/{wid}/runs/{parent['id']}/cancel").status_code == 200
    saved = detail(owner, wid, parent)
    assert all(row["state"] == "cancelled" for row in saved["children"])
    assert not run_once(application.state.session_factory)


def test_competing_workers_execute_once(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    run = start(owner, wid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: run_once(application.state.session_factory), range(2)))
    saved = detail(owner, wid, run)
    assert saved["state"] == "completed"
    assert len([event for event in saved["events"] if event["event"] == "started"]) == 1


@pytest.mark.parametrize(
    "action", ["approve", "reject", "expire", "tamper", "remove", "transfer", "changed"]
)
def test_bound_approval_lifecycle(accounts, application, action):
    owner, _ = accounts()
    member, data = accounts("bob@example.test")
    outsider, _ = accounts("other@example.test")
    wid = project(owner)
    join(owner, member, wid)
    t = task(owner, wid)
    run = start(member, wid, publish=True)
    drain(application)
    saved = detail(owner, wid, run)
    assert saved["state"] == "waiting_for_approval"
    approval = saved["approval"]
    url = f"/workspaces/{wid}/approvals/{approval['id']}"
    body = {"payload_hash": approval["payload_hash"]}
    assert member.post(f"{url}/approve", json=body).status_code == 403
    assert outsider.post(f"{url}/approve", json=body).status_code == 404
    assert owner.post(f"{url}/approve", json={"payload_hash": "0" * 64}).status_code == 409
    if action in {"expire", "tamper"}:
        with application.state.session_factory() as db:
            row = db.get(Approval, approval["id"])
            if action == "expire":
                row.expires_at = utc_now() - timedelta(seconds=1)
            else:
                row.payload = {**row.payload, "content": "Different action"}
            db.commit()
    response = owner.post(f"{url}/{'reject' if action == 'reject' else 'approve'}", json=body)
    if action == "tamper":
        assert response.status_code == 409
        assert owner.get(f"/workspaces/{wid}/messages").json() == []
        return
    if action == "expire":
        assert response.status_code == 409
    else:
        assert response.status_code == 200
    if action == "remove":
        owner.delete(f"/workspaces/{wid}/members/{data['id']}")
    elif action == "transfer":
        assert (
            owner.post(
                f"/workspaces/{wid}/transfer-ownership", json={"user_id": data["id"]}
            ).status_code
            == 200
        )
    elif action == "changed":
        owner.patch(
            f"/workspaces/{wid}/tasks/{t['id']}", json={"version": 1, "title": "After approval"}
        )
    drain(application)
    saved = detail(owner, wid, run)
    messages = owner.get(f"/workspaces/{wid}/messages").json()
    if action == "approve":
        assert saved["state"] == "completed" and saved["approval"]["state"] == "executed"
        assert len(messages) == 1 and messages[0]["content"] == approval["payload"]["content"]
        drain(application)
        assert len(owner.get(f"/workspaces/{wid}/messages").json()) == 1
    else:
        assert not messages
        assert saved["state"] == ("cancelled" if action == "reject" else "failed")
    assert owner.post(f"{url}/approve", json=body).status_code in {403, 409}


def test_all_intelligence_routes_fail_after_logout(accounts):
    owner, _ = accounts()
    wid = project(owner)
    run = start(owner, wid)
    owner.post("/auth/logout")
    for resource in [
        "decisions",
        "knowledge",
        "continuity",
        "runs",
        f"runs/{run['id']}",
        "approvals",
    ]:
        assert owner.get(f"/workspaces/{wid}/{resource}").status_code == 401


def test_missing_and_cross_workspace_agent_inputs_and_routes(accounts):
    owner, _ = accounts()
    outsider, _ = accounts("other@example.test")
    wid, other = project(owner), project(outsider)
    private = task(outsider, other)
    body = {
        "agent_type": "local.status.v1",
        "objective": "Inspect",
        "idempotency_key": "source-key-0001",
        "input_refs": [{"kind": "task", "id": private["id"]}],
    }
    assert owner.post(f"/workspaces/{wid}/runs", json=body).status_code == 404
    body["input_refs"] = []
    body["task_id"] = private["id"]
    assert owner.post(f"/workspaces/{wid}/runs", json=body).status_code == 409
    body["task_id"] = None
    body["agent_type"] = "execute.shell"
    assert owner.post(f"/workspaces/{wid}/runs", json=body).status_code == 422
    run = start(owner, wid)
    for path in ["runs", f"runs/{run['id']}", "approvals", "decisions", "continuity"]:
        assert outsider.get(f"/workspaces/{wid}/{path}").status_code == 404
    assert outsider.post(f"/workspaces/{wid}/runs/{run['id']}/cancel").status_code == 404


def test_approval_tampered_after_approval_cannot_execute(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    run = start(owner, wid, publish=True)
    drain(application)
    approval = detail(owner, wid, run)["approval"]
    assert (
        owner.post(
            f"/workspaces/{wid}/approvals/{approval['id']}/approve",
            json={"payload_hash": approval["payload_hash"]},
        ).status_code
        == 200
    )
    with application.state.session_factory() as db:
        record = db.get(Approval, approval["id"])
        record.payload = {**record.payload, "content": "Mutated after consent"}
        db.commit()
    drain(application)
    assert detail(owner, wid, run)["error_code"] == "approval_payload_mismatch"
    assert owner.get(f"/workspaces/{wid}/messages").json() == []


def test_competing_approval_and_rejection(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    run = start(owner, wid, publish=True)
    drain(application)
    approval = detail(owner, wid, run)["approval"]
    cookies = dict(owner.cookies)

    def respond(action):
        with TestClient(application) as browser:
            browser.cookies.update(cookies)
            return browser.post(
                f"/workspaces/{wid}/approvals/{approval['id']}/{action}",
                json={"payload_hash": approval["payload_hash"]},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(respond, ["approve", "reject"])) == [200, 409]
    drain(application)
    saved = detail(owner, wid, run)
    assert saved["state"] in {"completed", "cancelled"}
    assert len(owner.get(f"/workspaces/{wid}/messages").json()) == int(
        saved["state"] == "completed"
    )


def test_execution_timeout_and_bounded_scope(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    run = start(owner, wid)
    from orchestration import compute

    def expired(contract, context, children):
        with application.state.session_factory() as db:
            db.get(AgentRun, run["id"]).lease_until = utc_now() - timedelta(seconds=1)
            db.commit()
        return compute(contract, context, children)

    assert run_once(application.state.session_factory, expired)
    assert detail(owner, wid, run)["error_code"] == "execution_timeout"
    user_id = owner.get("/me").json()["id"]
    with application.state.session_factory() as db:
        db.add_all(
            [
                Task(
                    id=f"task-{i}",
                    workspace_id=wid,
                    creator_id=user_id,
                    title="Bounded task",
                    description="",
                    status="todo",
                    priority="medium",
                    version=1,
                )
                for i in range(501)
            ]
        )
        db.commit()
    bounded = start(owner, wid, idempotency_key="bounded-key-0001")
    drain(application)
    assert detail(owner, wid, bounded)["error_code"] == "scope_limit_exceeded"


def test_runs_survive_new_application_instance(accounts, application):
    from main import create_app

    owner, _ = accounts()
    wid = project(owner)
    run = start(owner, wid)
    replacement = create_app(application.state.settings)
    drain(replacement)
    with TestClient(replacement) as browser:
        browser.cookies.update(owner.cookies)
        saved = browser.get(f"/workspaces/{wid}/runs/{run['id']}").json()
        assert saved["state"] == "completed" and saved["outcome"]


def test_supersession_chain_and_cross_workspace_replacement(accounts):
    owner, _ = accounts()
    wid, other = project(owner), project(owner)
    first = decision(owner, wid, status="accepted")
    second = decision(owner, wid, status="accepted")
    third = decision(owner, wid, status="accepted")
    private = decision(owner, other, status="accepted")

    def replace(a, b):
        return owner.post(
            f"/workspaces/{wid}/decisions/{a['id']}/supersede",
            json={
                "version": 1,
                "successor_id": b["id"],
                "successor_version": 1,
                "reason": "New evidence",
            },
        )

    assert replace(first, private).status_code == 404
    assert replace(first, first).status_code == 409
    assert replace(first, second).status_code == 200
    assert replace(second, third).status_code == 200
    assert replace(third, first).status_code == 409
    current = owner.get(f"/workspaces/{wid}/knowledge?kind=decision").json()
    assert [row["id"] for row in current["items"]] == [third["id"]]


def test_coordinator_rejects_mixed_child_contexts(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    record = task(owner, wid)
    run = start(owner, wid, agent_type="local.handoff.v1")
    assert run_once(application.state.session_factory)
    assert (
        owner.patch(
            f"/workspaces/{wid}/tasks/{record['id']}",
            json={"version": 1, "title": "Changed between delegates"},
        ).status_code
        == 200
    )
    drain(application)
    saved = detail(owner, wid, run)
    assert saved["state"] == "failed" and saved["error_code"] == "context_changed"
    assert saved["outcome"] is None and len(saved["children"]) == 2


def test_handoff_capacity_is_atomic_for_three_records(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    user_id = owner.get("/me").json()["id"]
    with application.state.session_factory() as db:
        db.add_all(
            [
                AgentRun(
                    id=f"queued-{i}",
                    workspace_id=wid,
                    initiator_id=user_id,
                    agent_type="local.status.v1",
                    objective="Capacity",
                    input_refs=[],
                    publish=False,
                    request_hash="x" * 64,
                    state="queued",
                )
                for i in range(98)
            ]
        )
        db.commit()
    response = owner.post(
        f"/workspaces/{wid}/runs",
        json={
            "agent_type": "local.handoff.v1",
            "objective": "Cannot overfill",
            "idempotency_key": "capacity-key-0001",
        },
    )
    assert response.status_code == 409
    with application.state.session_factory() as db:
        assert db.query(AgentRun).count() == 98


def test_approved_request_expiring_before_worker_fails(accounts, application):
    owner, _ = accounts()
    wid = project(owner)
    run = start(owner, wid, publish=True)
    drain(application)
    approval = detail(owner, wid, run)["approval"]
    owner.post(
        f"/workspaces/{wid}/approvals/{approval['id']}/approve",
        json={"payload_hash": approval["payload_hash"]},
    )
    with application.state.session_factory() as db:
        db.get(Approval, approval["id"]).expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    drain(application)
    saved = detail(owner, wid, run)
    assert saved["state"] == "failed" and saved["approval"]["state"] == "expired"
    assert owner.get(f"/workspaces/{wid}/messages").json() == []


def test_database_cross_workspace_decision_and_run_constraints(accounts, application):
    from sqlalchemy.exc import IntegrityError

    from models import Decision

    owner, _ = accounts()
    wid, other = project(owner), project(owner)
    first = decision(owner, wid, status="accepted")
    second = decision(owner, other, status="accepted")
    other_task = task(owner, other)
    user_id = owner.get("/me").json()["id"]
    with application.state.session_factory() as db:
        record = db.get(Decision, first["id"])
        record.status, record.superseded_by_id = "superseded", second["id"]
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(
            AgentRun(
                id="invalid-run",
                workspace_id=wid,
                initiator_id=user_id,
                agent_type="local.status.v1",
                objective="Invalid task",
                task_id=other_task["id"],
                input_refs=[],
                publish=False,
                request_hash="x" * 64,
                state="queued",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
