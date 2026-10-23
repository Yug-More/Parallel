"""Durable deterministic local agents. No tools, shell, models or outbound I/O.

Workers claim a lease in a short workspace transaction, compute outside it, and
revalidate membership, dependencies and lease before committing an outcome.
A crashed lease fails visibly; only an explicit bounded retry creates new work.
"""

import hashlib
import json
import re
import time
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException

from collaboration import lock_workspace, record_activity
from knowledge_sources import resolve
from models import (
    ActionProposal,
    AgentRun,
    Approval,
    Decision,
    Membership,
    Message,
    RunEvent,
    Task,
    TaskDependency,
    User,
    Workspace,
    utc_now,
)
from provenance import source_record
from retrieval import retrieve
from security import as_utc

CONTRACTS = {
    "local.status.v1": {
        "name": "Project status",
        "description": "Counts tasks and records current accepted decisions with source references.",
        "input": "Workspace state and optional active task",
        "output": "Source-linked status facts",
    },
    "local.dependencies.v1": {
        "name": "Dependency analyst",
        "description": "Traverses task prerequisites, identifies unresolved chains and ready work.",
        "input": "Workspace task graph (may include blocked tasks)",
        "output": "Dependency chains and ready task references",
    },
    "local.handoff.v1": {
        "name": "Handoff coordinator",
        "description": "Delegates status and dependency analysis, then composes their verified results.",
        "input": "Workspace state and optional unblocked active task",
        "output": "Handoff report with child run provenance",
    },
}
CONTRACTS.update(
    {
        "local.plan.v1": {
            "name": "Task planner",
            "description": "Turns up to five explicit objective steps into a reviewable native task plan; skips existing titles.",
            "input": "Semicolon or newline-separated task titles and current workspace state",
            "output": "Exact create-task proposal; human owner approval required",
        },
        "local.research.v1": {
            "name": "Context researcher",
            "description": "Retrieves up to eight source excerpts, preserves citations and abstains without matching evidence.",
            "input": "Objective terms and authorized current/historical project knowledge",
            "output": "Source-linked context report, not a correctness guarantee",
        },
        "local.delivery.v1": {
            "name": "Delivery coordinator",
            "description": "Delegates a bounded task plan and context research, then composes consistent child reports.",
            "input": "Explicit objective steps and workspace context",
            "output": "Two child runs, reviewable plan and context evidence",
        },
    }
)
DELEGATES = {
    "local.handoff.v1": ["local.status.v1", "local.dependencies.v1"],
    "local.delivery.v1": ["local.plan.v1", "local.research.v1"],
}
KNOWLEDGE_CONTRACTS = {"local.plan.v1", "local.research.v1", "local.delivery.v1"}
TERMINAL = {"completed", "failed", "cancelled"}


class ExecutionError(Exception):
    pass


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def event(db, run, name, **detail):
    db.add(
        RunEvent(
            id=str(uuid4()), workspace_id=run.workspace_id, run_id=run.id, event=name, detail=detail
        )
    )


def task_scope(db, workspace_id, task_id, agent_type):
    if not task_id:
        return
    task = db.query(Task).filter_by(workspace_id=workspace_id, id=task_id).first()
    if not task or task.archived or task.status == "done":
        raise ExecutionError("task_unavailable")
    if agent_type != "local.dependencies.v1":
        prerequisites = (
            db.query(Task)
            .join(TaskDependency, Task.id == TaskDependency.depends_on_id)
            .filter(TaskDependency.workspace_id == workspace_id, TaskDependency.task_id == task_id)
            .all()
        )
        if task.status == "blocked" or any(t.status != "done" or t.archived for t in prerequisites):
            raise ExecutionError("task_blocked")


def create_run(
    db,
    workspace_id,
    actor_id,
    agent_type,
    objective,
    task_id,
    refs,
    publish,
    key,
    attempt=1,
    retry_of=None,
):
    request_hash = digest(
        {
            "agent_type": agent_type,
            "objective": objective,
            "task_id": task_id,
            "input_refs": refs,
            "publish": publish,
            "retry_of": retry_of,
        }
    )
    existing = (
        db.query(AgentRun)
        .filter_by(workspace_id=workspace_id, initiator_id=actor_id, idempotency_key=key)
        .first()
    )
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "Idempotency key is already bound to a different request")
        return existing
    if (
        db.query(AgentRun)
        .filter(
            AgentRun.workspace_id == workspace_id,
            AgentRun.state.in_(["queued", "running", "waiting_for_approval"]),
        )
        .count()
        + (3 if agent_type in DELEGATES else 1)
        > 100
    ):
        raise HTTPException(409, "Workspace has too many outstanding runs")
    try:
        task_scope(db, workspace_id, task_id, agent_type)
    except ExecutionError as exc:
        raise HTTPException(409, str(exc)) from None
    for ref in refs:
        source_record(db, workspace_id, ref["kind"], ref["id"])
    run = AgentRun(
        id=str(uuid4()),
        workspace_id=workspace_id,
        initiator_id=actor_id,
        agent_type=agent_type,
        objective=objective,
        task_id=task_id,
        input_refs=refs,
        publish=publish,
        idempotency_key=key,
        request_hash=request_hash,
        state="queued",
        attempt=attempt,
        retry_of_id=retry_of,
    )
    db.add(run)
    db.flush()
    event(db, run, "queued", contract=agent_type, task_id=task_id)
    if agent_type in DELEGATES:
        children = []
        for contract in DELEGATES[agent_type]:
            child = AgentRun(
                id=str(uuid4()),
                workspace_id=workspace_id,
                initiator_id=actor_id,
                agent_type=contract,
                objective=objective,
                task_id=task_id,
                input_refs=refs,
                publish=False,
                parent_id=run.id,
                request_hash=request_hash,
                state="queued",
                attempt=attempt,
            )
            db.add(child)
            db.flush()
            event(db, child, "delegated", parent_id=run.id, contract=contract)
            children.append(child.id)
        event(
            db,
            run,
            "plan_saved",
            steps=[*DELEGATES[agent_type], "Compose verified child results"],
            child_run_ids=children,
        )
    record_activity(
        db,
        workspace_id,
        db.get(User, actor_id),
        f"Queued {CONTRACTS[agent_type]['name']}: {objective}",
    )
    return run


def capture_context(db, run):
    from github_app import expire_workspace

    expire_workspace(db, run.workspace_id)
    task_scope(db, run.workspace_id, run.task_id, run.agent_type)
    tasks = (
        db.query(Task).filter_by(workspace_id=run.workspace_id).order_by(Task.id).limit(501).all()
    )
    decisions = (
        db.query(Decision)
        .filter_by(workspace_id=run.workspace_id, status="accepted")
        .order_by(Decision.id)
        .limit(201)
        .all()
    )
    edges = (
        db.query(TaskDependency)
        .filter_by(workspace_id=run.workspace_id)
        .order_by(TaskDependency.task_id, TaskDependency.depends_on_id)
        .limit(2501)
        .all()
    )
    if len(tasks) > 500 or len(decisions) > 200 or len(edges) > 2500:
        raise ExecutionError("scope_limit_exceeded")
    task_data = [
        {**source_record(db, run.workspace_id, "task", row.id), "assignee_id": row.assignee_id}
        for row in tasks
    ]
    decision_data = [source_record(db, run.workspace_id, "decision", row.id) for row in decisions]
    graph = [{"task_id": row.task_id, "depends_on_id": row.depends_on_id} for row in edges]
    inputs = [source_record(db, run.workspace_id, ref["kind"], ref["id"]) for ref in run.input_refs]
    knowledge = []
    if run.agent_type in KNOWLEDGE_CONTRACTS:
        matches = []
        for kind in ["decision", "decision_revision", "task", "document", "external", "message"]:
            matches.extend(
                item
                for item in retrieve(
                    db,
                    run.workspace_id,
                    q=""
                    if run.objective.casefold().strip() == "triage github issues"
                    and kind == "external"
                    else run.objective[:200],
                    status="open"
                    if run.objective.casefold().strip() == "triage github issues"
                    and kind == "external"
                    else None,
                    kind=kind,
                    limit=8,
                    include_historical=kind in {"document", "decision_revision"},
                )["items"]
                if item["authority"] != "interpretation"
            )
        matches.sort(key=lambda item: (-item["score"], item["kind"], item["id"]))
        for item in matches[:8]:
            knowledge.append(resolve(db, run.workspace_id, item["kind"], item["id"]))
    epoch = db.get(Workspace, run.workspace_id).knowledge_epoch
    fingerprint_data = {
        "tasks": task_data,
        "decisions": decision_data,
        "edges": graph,
        "inputs": inputs,
    }
    if run.agent_type in KNOWLEDGE_CONTRACTS:
        fingerprint_data.update(knowledge=knowledge, knowledge_epoch=epoch)
    # Keep the original contracts' fingerprint format compatible with Phase 3
    # pending approvals/children; epoch checks below independently gate new reports.
    fingerprint = digest(fingerprint_data)
    return {
        "as_of": as_utc(utc_now()).isoformat(),
        "workspace_id": run.workspace_id,
        "tasks": task_data,
        "objective": run.objective,
        "knowledge_sources": knowledge,
        "knowledge_epoch": epoch,
        "decisions": decision_data,
        "edges": graph,
        "input_sources": inputs,
        "fingerprint": fingerprint,
        "scope": "All tasks (up to 500), accepted decisions (up to 200), up to 2500 edges, and explicit sources. No model synthesis.",
    }


def reference(item):
    return {"kind": item["kind"], "id": item["id"], "version": item["version"]}


def compute(contract, context, children=None):
    deadline = time.monotonic() + 30
    tasks = {row["id"]: row for row in context["tasks"]}
    active = [row for row in tasks.values() if not row["archived"]]
    facts = []
    chains = []
    ready = []
    proposal = None
    if contract == "local.status.v1":
        counts = {
            state: sum(row["status"] == state for row in active)
            for state in ["todo", "in_progress", "blocked", "done"]
        }
        facts = [
            {"text": f"{row['title']} — {row['status']}", "sources": [reference(row)]}
            for row in active
        ]
        facts.extend(
            {"text": f"Accepted decision: {row['title']}", "sources": [reference(row)]}
            for row in context["decisions"]
        )
        summary = f"{len(active)} active tasks; {counts['done']} done, {counts['blocked']} explicitly blocked. {len(context['decisions'])} accepted decisions."
    elif contract == "local.dependencies.v1":
        graph = {}
        for edge in context["edges"]:
            graph.setdefault(edge["task_id"], []).append(edge["depends_on_id"])
        for row in active:
            if time.monotonic() > deadline:
                raise ExecutionError("execution_timeout")
            if row["status"] == "done":
                continue
            pending, visited, unresolved = (
                [(x, [row["id"], x]) for x in graph.get(row["id"], [])],
                set(),
                [],
            )
            while pending:
                node, path = pending.pop()
                if node in visited:
                    continue
                visited.add(node)
                if len(path) > 100 or len(chains) > 2500:
                    raise ExecutionError("analysis_limit_exceeded")
                if node not in tasks:
                    raise ExecutionError("invalid_dependency")
                prerequisite = tasks[node]
                if prerequisite["status"] != "done":
                    unresolved.append(node)
                    chains.append(
                        {
                            "task_id": row["id"],
                            "path": path,
                            "sources": [reference(tasks[part]) for part in path],
                        }
                    )
                pending.extend((x, [*path, x]) for x in graph.get(node, []) if x not in path)
            if unresolved or row["status"] == "blocked":
                facts.append(
                    {
                        "text": f"{row['title']}: {len(unresolved)} unresolved prerequisite(s)"
                        + ("; explicitly Blocked" if row["status"] == "blocked" else ""),
                        "sources": [reference(row), *[reference(tasks[x]) for x in unresolved]],
                    }
                )
            else:
                ready.append(reference(row))
        summary = f"{len(facts)} open tasks have blockers; {len(ready)} open tasks are ready by dependency state. Readiness is not a completion claim."
    elif contract == "local.plan.v1":
        titles, seen = [], set()
        for part in re.split(r"[;\n]+", context["objective"]):
            title = re.sub(r"^(?:[-•]\s+|\d+[.)]\s+)", "", part.strip(), count=1)[:200].strip()
            if title and title.casefold() not in seen:
                titles.append(title)
                seen.add(title.casefold())
        if len(titles) > 5:
            raise ExecutionError("plan_step_limit")
        existing = {row["title"].casefold() for row in active}
        steps = [
            {
                "title": title,
                "description": "Proposed from explicit objective. Human review and execution required.",
                "status": "todo",
                "priority": "medium",
                "assignee_id": None,
            }
            for title in titles
            if title and title.casefold() not in existing
        ]
        dependency_report = compute("local.dependencies.v1", context)
        chains, ready = (
            dependency_report["dependency_chains"][:100],
            dependency_report["ready_tasks"][:20],
        )
        blocker_ids = {
            ref["id"] for fact in dependency_report["facts"][:10] for ref in fact["sources"]
        }
        plan_sources = [
            *context["knowledge_sources"],
            *[row for row in context["tasks"] if row["id"] in blocker_ids][:10],
            *context["decisions"][:3],
        ]
        evidence, seen_refs = [], set()
        for source in plan_sources:
            key = (source["kind"], source["id"])
            if key not in seen_refs and len(evidence) < 20:
                evidence.append(reference(source))
                seen_refs.add(key)
        if context["objective"].casefold().strip() == "triage github issues":
            issues = [
                s
                for s in context["knowledge_sources"]
                if s["kind"] == "external"
                and s.get("record_type") == "issues"
                and s["status"] == "open"
            ]
            steps = [
                {
                    "title": ("Review issue: " + s["title"])[:200],
                    "description": "Imported GitHub issue; inspect before implementation.\n"
                    + s["original_url"]
                    + "\nSource: external:"
                    + s["id"]
                    + " version "
                    + str(s["version"]),
                    "status": "todo",
                    "priority": "medium",
                    "assignee_id": None,
                }
                for s in issues
                if ("Review issue: " + s["title"])[:200].casefold() not in existing
            ][:5]
            evidence = [reference(s) for s in issues[:5]]
        if steps:
            proposal = {
                "action": "create_task_plan",
                "tasks": steps,
                "sequential_dependencies": context["objective"].casefold().strip()
                != "triage github issues",
                "evidence": evidence,
            }
        summary = f"{len(dependency_report['facts'])} existing blocked task(s); {len(ready)} existing ready task(s). {len(steps)} proposed task(s); {len(titles) - len(steps)} existing or empty title(s) skipped. Objective steps preserve your wording. No work was executed."
        if context["objective"].casefold().strip() == "triage github issues":
            summary = f"{len(steps)} open GitHub issue task(s) proposed from authorized imported evidence. No tasks created; owner approval required. Separate issues have no inferred dependencies."
        facts = [
            {"text": "Existing task: " + row["title"], "sources": [reference(row)]}
            for row in active
            if row["title"].casefold() in {title.casefold() for title in titles}
        ]
        facts.extend(dependency_report["facts"][:10])
        facts.extend(
            {"text": "Accepted decision to review: " + row["title"], "sources": [reference(row)]}
            for row in context["decisions"][:3]
        )
    elif contract == "local.research.v1":
        sources = context["knowledge_sources"]
        facts = [
            {
                "text": f"{row['kind']} · {row['status'] or 'record'}"
                + (f" · version {row['version']}" if row["version"] else "")
                + ":\n"
                + (row["body"][:1500] or row["title"]),
                "sources": [reference(row)],
            }
            for row in sources
        ]
        historical = sum(
            row["kind"] == "decision_revision" or row["status"] == "historical" for row in sources
        )
        summary = (
            f"{len(sources)} matching source excerpt(s), including {historical} historical snapshot(s). Check current decisions and inspect each source; lexical matches can be incomplete or contradictory."
            if sources
            else "Abstained: no matching project evidence. Try specific terms or add context."
        )
    elif contract in {"local.handoff.v1", "local.delivery.v1"}:
        if not children or any(
            child["context"]["fingerprint"] != context["fingerprint"] for child in children
        ):
            raise ExecutionError("context_changed")
        facts = [fact for child in children for fact in child["outcome"]["facts"]]
        summary = "\n".join(child["outcome"]["summary"] for child in children)
        if contract == "local.delivery.v1":
            proposal = next(
                (
                    child["outcome"].get("proposal")
                    for child in children
                    if child["outcome"].get("proposal")
                ),
                None,
            )
    else:
        raise ExecutionError("unsupported_contract")
    return {
        "contract": contract,
        "summary": summary,
        "facts": facts,
        "proposal": proposal,
        "dependency_chains": chains,
        "ready_tasks": ready,
        "as_of": context["as_of"],
        "scope": context["scope"],
        "child_run_ids": [child["id"] for child in children or []],
        "interpretation": "Deterministic computation over persisted records. No external work was executed; no task status changed.",
    }


def fail(db, run, code):
    run.state, run.error_code, run.completed_at = "failed", code, utc_now()
    run.lease_token, run.lease_until = None, None
    event(db, run, "failed", code=code)


def cancel_tree(db, run, actor_id):
    for item in [
        run,
        *db.query(AgentRun).filter_by(workspace_id=run.workspace_id, parent_id=run.id).all(),
    ]:
        if item.state in TERMINAL:
            continue
        item.state, item.completed_at, item.lease_token, item.lease_until = (
            "cancelled",
            utc_now(),
            None,
            None,
        )
        approval = (
            db.query(Approval).filter_by(workspace_id=item.workspace_id, run_id=item.id).first()
        )
        if approval and approval.state in {"pending", "approved"}:
            approval.state = "cancelled"
        proposal = (
            db.query(ActionProposal)
            .filter_by(workspace_id=item.workspace_id, run_id=item.id)
            .first()
        )
        if proposal and proposal.state in {"pending", "approved"}:
            proposal.state = "cancelled"
        event(db, item, "cancelled", actor_id=actor_id)


def publication_payload(run):
    facts = run.outcome["facts"][:20]
    content = f"Local agent report: {run.objective}\nAs of {run.outcome['as_of']}\n\n{run.outcome['summary']}\n\n"
    content += "\n".join(
        f"• {fact['text']} ["
        + ", ".join(f"{s['kind']}:{s['id']}" for s in fact["sources"][:10])
        + "]"
        for fact in facts
    )
    content += f"\n\n{run.outcome['interpretation']}\nFull report: run {run.id}. Publication includes up to 20 facts."
    return {
        "workspace_id": run.workspace_id,
        "run_id": run.id,
        "agent_type": run.agent_type,
        "content": content,
    }


def execute_approval(db, approval, run):
    now = utc_now()
    if approval.expires_at <= now:
        approval.state = "expired"
        fail(db, run, "approval_expired")
        return
    if approval.state != "approved":
        return
    owner = db.get(Membership, (run.workspace_id, approval.approver_id))
    try:
        if not db.get(Membership, (run.workspace_id, run.initiator_id)):
            raise ExecutionError("initiator_removed")
        if not owner or owner.role != "owner":
            raise ExecutionError("approver_no_longer_owner")
        if (
            approval.action != "publish_report"
            or digest(approval.payload) != approval.payload_hash
            or approval.payload != publication_payload(run)
        ):
            raise ExecutionError("approval_payload_mismatch")
        current_context = capture_context(db, run)
        if (
            current_context["fingerprint"] != run.context["fingerprint"]
            or run.context.get("knowledge_epoch", current_context["knowledge_epoch"])
            != current_context["knowledge_epoch"]
        ):
            raise ExecutionError("context_changed")
        message = Message(
            id=str(uuid4()),
            workspace_id=run.workspace_id,
            user_id=run.initiator_id,
            sender_id=run.agent_type,
            sender_name=CONTRACTS[run.agent_type]["name"],
            role="assistant",
            content=approval.payload["content"],
            knowledge_epoch=(run.context or {}).get("knowledge_epoch"),
        )
        db.add(message)
        db.flush()
        approval.state, approval.message_id, approval.executed_at = "executed", message.id, now
        run.state, run.completed_at = "completed", now
        event(
            db,
            run,
            "published",
            approval_id=approval.id,
            message_id=message.id,
            approver_id=approval.approver_id,
        )
        record_activity(
            db,
            run.workspace_id,
            db.get(User, approval.approver_id),
            f"Published approved local report: {run.objective}",
        )
    except ExecutionError as exc:
        approval.state, approval.error_code = "failed", str(exc)
        fail(db, run, str(exc))


def run_once(session_factory, compute_fn=compute):
    """One recovery, approval execution or job. Safe to call from multiple workers."""
    with session_factory() as db:
        expired = (
            db.query(AgentRun)
            .filter(AgentRun.state == "running", AgentRun.lease_until <= utc_now())
            .order_by(AgentRun.lease_until)
            .first()
        )
        if expired:
            lock_workspace(db, expired.workspace_id)
            db.refresh(expired)
            if expired.state == "running" and expired.lease_until <= utc_now():
                fail(db, expired, "lease_expired")
                db.commit()
                return True
            db.rollback()  # release a stale recovery candidate before locking another workspace
        candidates = (
            db.query(Approval.id, Approval.workspace_id)
            .filter(
                (Approval.state == "approved")
                | ((Approval.state == "pending") & (Approval.expires_at <= utc_now()))
            )
            .order_by(Approval.created_at, Approval.id)
            .limit(1)
            .all()
        )
        if candidates:
            approval_id, workspace_id = candidates[0]
            lock_workspace(db, workspace_id)
            approval = db.get(Approval, approval_id, populate_existing=True)
            run = db.get(AgentRun, approval.run_id, populate_existing=True)
            if approval.state in {"pending", "approved"} and run.state == "waiting_for_approval":
                execute_approval(db, approval, run)
            db.commit()
            return True
        candidates = (
            db.query(AgentRun.id, AgentRun.workspace_id)
            .filter_by(state="queued")
            .order_by(AgentRun.created_at, AgentRun.id)
            .limit(100)
            .all()
        )
    for run_id, workspace_id in candidates:
        with session_factory() as db:
            lock_workspace(db, workspace_id)
            run = db.get(AgentRun, run_id, populate_existing=True)
            if run.state != "queued":
                continue
            if not db.get(Membership, (workspace_id, run.initiator_id)):
                fail(db, run, "initiator_removed")
                db.commit()
                return True
            children = (
                db.query(AgentRun)
                .filter_by(workspace_id=workspace_id, parent_id=run.id)
                .order_by(AgentRun.agent_type)
                .all()
            )
            if any(child.state in {"failed", "cancelled"} for child in children):
                fail(db, run, "delegation_failed")
                db.commit()
                return True
            if any(child.state != "completed" for child in children):
                continue
            try:
                context = capture_context(db, run)
            except (ExecutionError, HTTPException) as exc:
                fail(db, run, str(exc) if isinstance(exc, ExecutionError) else "source_unavailable")
                db.commit()
                return True
            token = str(uuid4())
            run.state, run.lease_token, run.lease_until = (
                "running",
                token,
                utc_now() + timedelta(seconds=60),
            )
            run.started_at, run.context = utc_now(), context
            event(db, run, "started", lease_seconds=60, context_fingerprint=context["fingerprint"])
            contract = run.agent_type
            child_data = [
                {"id": child.id, "context": child.context, "outcome": child.outcome}
                for child in children
            ]
            db.commit()
        try:
            outcome = compute_fn(contract, context, child_data)
            code = None
        except Exception as exc:
            outcome, code = (
                None,
                str(exc) if isinstance(exc, ExecutionError) else "execution_failed",
            )
        with session_factory() as db:
            lock_workspace(db, workspace_id)
            run = db.get(AgentRun, run_id, populate_existing=True)
            if run.state != "running" or run.lease_token != token:
                return True  # cancellation/recovery won; discard late computation
            try:
                if run.lease_until <= utc_now():
                    raise ExecutionError("execution_timeout")
                if not db.get(Membership, (workspace_id, run.initiator_id)):
                    raise ExecutionError("initiator_removed")
                current_context = capture_context(db, run)
                if (
                    current_context["fingerprint"] != context["fingerprint"]
                    or current_context["knowledge_epoch"] != context["knowledge_epoch"]
                ):
                    raise ExecutionError("context_changed")
                if code:
                    raise ExecutionError(code)
                run.outcome, run.lease_token, run.lease_until = outcome, None, None
                if outcome.get("proposal") and run.parent_id is None:
                    action_payload = {
                        "run_id": run.id,
                        "context_fingerprint": context["fingerprint"],
                        "proposal": outcome["proposal"],
                    }
                    proposal = ActionProposal(
                        id=str(uuid4()),
                        workspace_id=workspace_id,
                        run_id=run.id,
                        action=outcome["proposal"]["action"],
                        payload=action_payload,
                        payload_hash=digest(action_payload),
                        state="pending",
                        expires_at=utc_now() + timedelta(hours=24),
                    )
                    db.add(proposal)
                    event(
                        db,
                        run,
                        "native_action_proposed",
                        proposal_id=proposal.id,
                        payload_hash=proposal.payload_hash,
                    )
                if run.publish:
                    payload = publication_payload(run)
                    approval = Approval(
                        id=str(uuid4()),
                        workspace_id=workspace_id,
                        run_id=run.id,
                        action="publish_report",
                        payload=payload,
                        payload_hash=digest(payload),
                        state="pending",
                        expires_at=utc_now() + timedelta(hours=24),
                    )
                    db.add(approval)
                    run.state = "waiting_for_approval"
                    event(
                        db,
                        run,
                        "approval_requested",
                        approval_id=approval.id,
                        payload_hash=approval.payload_hash,
                    )
                else:
                    run.state, run.completed_at = "completed", utc_now()
                    event(db, run, "completed", fact_count=len(outcome["facts"]))
                record_activity(
                    db,
                    workspace_id,
                    db.get(User, run.initiator_id),
                    f"Local {CONTRACTS[contract]['name']}: {run.state.replace('_', ' ')}",
                )
            except (ExecutionError, HTTPException) as exc:
                fail(db, run, str(exc) if isinstance(exc, ExecutionError) else "source_unavailable")
            db.commit()
            return True
    return False
