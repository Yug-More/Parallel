"""Bounded live overview; source text is resolved through existing scoped APIs."""

from fastapi import APIRouter
from sqlalchemy import func

from api.intelligence import briefing
from models import ActionProposal, AgentRun, Decision, Document, RepositoryConnection, utc_now
from security import DB, CurrentUser, require_member
from worker_health import status as worker_status

router = APIRouter()


@router.get("/workspaces/{workspace_id}/overview")
def overview(workspace_id: str, user: CurrentUser, db: DB):
    require_member(db, user.id, workspace_id)
    continuity = briefing(workspace_id, user, db, since=None, limit=5, offset=0)
    documents = (
        db.query(func.count())
        .select_from(Document)
        .filter_by(workspace_id=workspace_id, archived=False)
        .scalar()
    )
    connections = (
        db.query(func.count())
        .select_from(RepositoryConnection)
        .filter_by(workspace_id=workspace_id, active=True)
        .scalar()
    )
    runs = (
        db.query(AgentRun)
        .filter_by(workspace_id=workspace_id, parent_id=None)
        .order_by(AgentRun.created_at.desc(), AgentRun.id)
        .limit(5)
        .all()
    )
    return {
        **continuity,
        "pending_native_actions": db.query(ActionProposal)
        .filter(
            ActionProposal.workspace_id == workspace_id,
            ActionProposal.state == "pending",
            ActionProposal.expires_at > utc_now(),
        )
        .count(),
        "worker": worker_status(db),
        "documents": documents,
        "connections": connections,
        "current_decisions": [
            {"id": row.id, "title": row.title, "version": row.version}
            for row in db.query(Decision)
            .filter_by(workspace_id=workspace_id, status="accepted")
            .order_by(Decision.updated_at.desc(), Decision.id)
            .limit(5)
        ],
        "recent_runs": [
            {
                "id": row.id,
                "agent_type": row.agent_type,
                "state": row.state,
                "objective": row.objective,
            }
            for row in runs
        ],
    }
