"""Exact native task-plan approval execution with atomic resource receipts."""

from uuid import uuid4

from fastapi import HTTPException

from collaboration import lock_workspace, record_activity
from knowledge_lifecycle import visible
from models import ActionProposal, AgentRun, Membership, Task, TaskDependency, User, utc_now
from orchestration import ExecutionError, capture_context, compute, digest, event
from security import as_utc


def proposal_out(db, proposal):
    run = db.get(AgentRun, proposal.run_id)
    available = visible(db, run)
    return {
        "id": proposal.id,
        "run_id": proposal.run_id,
        "action": proposal.action,
        "payload": proposal.payload if available else None,
        "payload_hash": proposal.payload_hash,
        "state": "expired"
        if proposal.state == "pending" and proposal.expires_at <= utc_now()
        else proposal.state,
        "evidence_unavailable": not available,
        "receipt": proposal.receipt,
        "error_code": proposal.error_code,
        "approver_id": proposal.approver_id,
        "created_at": as_utc(proposal.created_at),
        "expires_at": as_utc(proposal.expires_at),
        "executed_at": as_utc(proposal.executed_at),
    }


def execute_once(factory):
    with factory() as db:
        row = (
            db.query(ActionProposal)
            .filter(
                (ActionProposal.state == "approved")
                | ((ActionProposal.state == "pending") & (ActionProposal.expires_at <= utc_now()))
            )
            .order_by(ActionProposal.created_at, ActionProposal.id)
            .first()
        )
        if not row:
            return False
        lock_workspace(db, row.workspace_id)
        db.refresh(row)
        if row.state not in {"approved", "pending"}:
            return True
        if row.expires_at <= utc_now():
            row.state = "expired"
            db.commit()
            return True
        if row.state != "approved":
            return True
        run = db.get(AgentRun, row.run_id)
        try:
            owner = db.get(Membership, (row.workspace_id, row.approver_id))
            if not owner or owner.role != "owner":
                raise ExecutionError("approver_no_longer_owner")
            if not db.get(Membership, (row.workspace_id, run.initiator_id)):
                raise ExecutionError("initiator_removed")
            if run.state not in {"completed", "waiting_for_approval"}:
                raise ExecutionError("run_unavailable")
            context = capture_context(db, run)
            expected_plan = compute("local.plan.v1", context)["proposal"]
            expected_payload = {
                "run_id": run.id,
                "context_fingerprint": context["fingerprint"],
                "proposal": expected_plan,
            }
            if not visible(db, run) or context["fingerprint"] != run.context["fingerprint"]:
                raise ExecutionError("context_changed")
            if (
                row.action != "create_task_plan"
                or row.payload != expected_payload
                or digest(row.payload) != row.payload_hash
            ):
                raise ExecutionError("proposal_payload_mismatch")
            tasks = expected_plan["tasks"]
            if not 1 <= len(tasks) <= 5:
                raise ExecutionError("plan_step_limit")
            resources, previous = [], None
            # All validation precedes writes; one workspace lock serializes every resource and receipt.
            for item in tasks:
                task = Task(
                    id=str(uuid4()),
                    workspace_id=row.workspace_id,
                    creator_id=run.initiator_id,
                    title=item["title"],
                    description=item["description"],
                    status="todo",
                    priority="medium",
                    assignee_id=None,
                    version=1,
                )
                db.add(task)
                db.flush()
                if previous and expected_plan["sequential_dependencies"]:
                    db.add(
                        TaskDependency(
                            workspace_id=row.workspace_id, task_id=task.id, depends_on_id=previous
                        )
                    )
                resources.append({"kind": "task", "id": task.id, "version": 1})
                previous = task.id
            row.receipt = {
                "proposal_id": row.id,
                "payload_hash": row.payload_hash,
                "resources": resources,
                "executed_by": row.approver_id,
            }
            row.state, row.executed_at = "executed", utc_now()
            event(
                db,
                run,
                "native_action_executed",
                proposal_id=row.id,
                resource_ids=[r["id"] for r in resources],
            )
            record_activity(
                db,
                row.workspace_id,
                db.get(User, row.approver_id),
                f"Applied approved task plan: {len(resources)} tasks created; execution still required",
            )
        except (ExecutionError, HTTPException) as exc:
            row.state = "failed"
            row.error_code = str(exc) if isinstance(exc, ExecutionError) else "source_unavailable"
        db.commit()
    return True
