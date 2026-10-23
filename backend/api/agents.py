"""Human-controlled local agent coordination and owner-bound publication approvals."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field

from collaboration import lock_workspace, record_activity
from knowledge_lifecycle import visible
from models import ActionProposal, AgentRun, Approval, RunEvent, utc_now
from orchestration import CONTRACTS, TERMINAL, cancel_tree, create_run, digest, event, fail
from provenance import SourceRef
from security import DB, CurrentUser, InputModel, as_utc, require_member

router = APIRouter()
AgentType = Literal[
    "local.status.v1",
    "local.dependencies.v1",
    "local.handoff.v1",
    "local.plan.v1",
    "local.research.v1",
    "local.delivery.v1",
]


class RunInput(InputModel):
    agent_type: AgentType
    objective: str = Field(min_length=1, max_length=1000)
    task_id: str | None = Field(None, min_length=1, max_length=100)
    input_refs: list[SourceRef] = Field(default_factory=list, max_length=30)
    publish: bool = False
    idempotency_key: str = Field(min_length=8, max_length=100)


class RetryInput(InputModel):
    idempotency_key: str = Field(min_length=8, max_length=100)


def run_out(run, db):
    output = {
        key: (as_utc(getattr(run, key)) if key.endswith("_at") else getattr(run, key))
        for key in (
            "id",
            "workspace_id",
            "initiator_id",
            "agent_type",
            "objective",
            "task_id",
            "parent_id",
            "input_refs",
            "publish",
            "state",
            "attempt",
            "retry_of_id",
            "outcome",
            "error_code",
            "created_at",
            "started_at",
            "completed_at",
        )
    }
    if not visible(db, run):
        output["outcome"] = None
        output["evidence_unavailable"] = True
        output["input_refs"] = []
    return output


def get_run(db, workspace_id, run_id):
    row = db.query(AgentRun).filter_by(workspace_id=workspace_id, id=run_id).first()
    if not row:
        raise HTTPException(404, "Run not found")
    return row


def approval_out(approval, db):
    data = {
        key: getattr(approval, key)
        for key in (
            "id",
            "workspace_id",
            "run_id",
            "action",
            "payload",
            "payload_hash",
            "state",
            "approver_id",
            "message_id",
            "error_code",
        )
    }
    if data["state"] in {"pending", "approved"} and approval.expires_at <= utc_now():
        data["state"] = "expired"
    for key in ["created_at", "expires_at", "responded_at", "executed_at"]:
        data[key] = as_utc(getattr(approval, key))
    if not visible(db, db.get(AgentRun, approval.run_id)):
        data["payload"] = None
        data["evidence_unavailable"] = True
    return data


@router.get("/agent-contracts")
def contracts(user: CurrentUser):
    return [
        {
            "id": key,
            **value,
            "mode": "deterministic_local",
            "external_actions": False,
            "approval": "Current owner approval is required for exact report publication and native task-plan execution; no work is automatically marked done.",
        }
        for key, value in CONTRACTS.items()
    ]


@router.post("/workspaces/{workspace_id}/runs", status_code=201)
def start(workspace_id: str, payload: RunInput, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    run = create_run(
        db,
        workspace_id,
        user.id,
        payload.agent_type,
        payload.objective,
        payload.task_id,
        [ref.model_dump() for ref in payload.input_refs],
        payload.publish,
        payload.idempotency_key,
    )
    db.commit()
    return run_out(run, db)


@router.get("/workspaces/{workspace_id}/runs")
def runs(
    workspace_id: str,
    user: CurrentUser,
    db: DB,
    state: str | None = Query(None, max_length=32),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
):
    require_member(db, user.id, workspace_id)
    query = db.query(AgentRun).filter_by(workspace_id=workspace_id, parent_id=None)
    if state:
        query = query.filter_by(state=state)
    return {
        "total": query.count(),
        "items": [
            run_out(row, db)
            for row in query.order_by(AgentRun.created_at.desc(), AgentRun.id)
            .offset(offset)
            .limit(limit)
        ],
    }


@router.get("/workspaces/{workspace_id}/runs/{run_id}")
def detail(workspace_id: str, run_id: str, user: CurrentUser, db: DB):
    require_member(db, user.id, workspace_id)
    run = get_run(db, workspace_id, run_id)
    approval = db.query(Approval).filter_by(workspace_id=workspace_id, run_id=run_id).first()
    return {
        **run_out(run, db),
        "context": run.context if visible(db, run) else None,
        "children": [
            run_out(row, db)
            for row in db.query(AgentRun)
            .filter_by(workspace_id=workspace_id, parent_id=run_id)
            .order_by(AgentRun.agent_type)
        ],
        "events": [
            {
                "id": row.id,
                "event": row.event,
                "detail": row.detail,
                "created_at": as_utc(row.created_at),
            }
            for row in db.query(RunEvent)
            .filter_by(workspace_id=workspace_id, run_id=run_id)
            .order_by(RunEvent.created_at, RunEvent.id)
            .limit(100)
        ],
        "approval": approval_out(approval, db) if approval else None,
    }


@router.post("/workspaces/{workspace_id}/runs/{run_id}/cancel")
def cancel(workspace_id: str, run_id: str, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    run = get_run(db, workspace_id, run_id)
    membership = require_member(db, user.id, workspace_id)
    if user.id != run.initiator_id and membership.role != "owner":
        raise HTTPException(403, "Only the initiator or owner can cancel")
    if run.parent_id:
        raise HTTPException(409, "Cancel the coordinator run to cancel its pending delegates")
    if run.state in TERMINAL:
        raise HTTPException(409, "Run is already terminal")
    cancel_tree(db, run, user.id)
    record_activity(db, workspace_id, user, f"Cancelled local run: {run.objective}")
    db.commit()
    return run_out(run, db)


@router.post("/workspaces/{workspace_id}/runs/{run_id}/retry", status_code=201)
def retry(workspace_id: str, run_id: str, payload: RetryInput, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    run = get_run(db, workspace_id, run_id)
    if run.parent_id or run.initiator_id != user.id:
        raise HTTPException(
            403, "Only the original initiator can retry a coordinator or standalone run"
        )
    if run.state != "failed" or run.attempt >= 3:
        raise HTTPException(409, "Only failed runs below the three-attempt limit can be retried")
    existing = db.query(AgentRun).filter_by(workspace_id=workspace_id, retry_of_id=run.id).first()
    if existing:
        if existing.idempotency_key != payload.idempotency_key:
            raise HTTPException(409, "This failed run already has a retry")
        return run_out(existing, db)
    new = create_run(
        db,
        workspace_id,
        user.id,
        run.agent_type,
        run.objective,
        run.task_id,
        run.input_refs,
        run.publish,
        payload.idempotency_key,
        run.attempt + 1,
        run.id,
    )
    db.commit()
    return run_out(new, db)


@router.get("/workspaces/{workspace_id}/approvals")
def approvals(
    workspace_id: str,
    user: CurrentUser,
    db: DB,
    pending: bool = False,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
):
    require_member(db, user.id, workspace_id)
    query = db.query(Approval).filter_by(workspace_id=workspace_id)
    if pending:
        query = query.filter(Approval.state == "pending", Approval.expires_at > utc_now())
    return {
        "total": query.count(),
        "items": [
            approval_out(row, db)
            for row in query.order_by(Approval.created_at.desc(), Approval.id)
            .offset(offset)
            .limit(limit)
        ],
    }


class ApprovalResponse(InputModel):
    payload_hash: str = Field(min_length=64, max_length=64)


@router.post("/workspaces/{workspace_id}/approvals/{approval_id}/{action}")
def respond(
    workspace_id: str,
    approval_id: str,
    action: Literal["approve", "reject"],
    payload: ApprovalResponse,
    user: CurrentUser,
    db: DB,
):
    lock_workspace(db, workspace_id, user.id, owner=True)
    item = db.query(Approval).filter_by(workspace_id=workspace_id, id=approval_id).first()
    if not item:
        raise HTTPException(404, "Approval not found")
    run = get_run(db, workspace_id, item.run_id)
    if item.state != "pending" or run.state != "waiting_for_approval":
        raise HTTPException(409, "Approval is no longer pending")
    if item.expires_at <= utc_now():
        item.state = "expired"
        fail(db, run, "approval_expired")
        db.commit()
        raise HTTPException(409, "Approval has expired")
    if action == "approve" and not visible(db, run):
        raise HTTPException(409, "Source knowledge changed; request a new report")
    if payload.payload_hash != item.payload_hash or digest(item.payload) != item.payload_hash:
        raise HTTPException(409, "Approval payload changed; refresh and inspect it")
    item.state, item.approver_id, item.responded_at = (
        ("approved" if action == "approve" else "rejected"),
        user.id,
        utc_now(),
    )
    event(
        db,
        run,
        f"approval_{item.state}",
        approval_id=item.id,
        actor_id=user.id,
        payload_hash=item.payload_hash,
    )
    if action == "reject":
        proposal = (
            db.query(ActionProposal).filter_by(workspace_id=workspace_id, run_id=run.id).first()
        )
        if proposal and proposal.state in {"pending", "approved"}:
            proposal.state = "cancelled"
        run.state, run.completed_at, run.error_code = "cancelled", utc_now(), "publication_rejected"
    record_activity(db, workspace_id, user, f"{item.state.title()} publication: {run.objective}")
    db.commit()
    return approval_out(item, db)


@router.post("/workspaces/{workspace_id}/runs/{run_id}/reasoning", status_code=201)
def reasoning(
    workspace_id: str, run_id: str, payload: RetryInput, user: CurrentUser, db: DB, request: Request
):
    """Explicit optional cited interpretation; never changes a run/proposal/action."""
    from api.answers import Question, answer

    require_member(db, user.id, workspace_id)
    run = db.query(AgentRun).filter_by(id=run_id, workspace_id=workspace_id).first()
    if not run or not visible(db, run):
        raise HTTPException(404, "Run evidence unavailable")
    if len(run.objective) > 200:
        raise HTTPException(422, "Use Ask workspace for a shorter evidence question")
    return answer(
        workspace_id,
        Question(question=run.objective, mode="model", idempotency_key=payload.idempotency_key),
        user,
        db,
        request,
    )
