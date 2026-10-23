"""Owner-only exact-payload native proposal decisions."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field

from actions import proposal_out
from collaboration import lock_workspace
from knowledge_lifecycle import visible
from models import ActionProposal, AgentRun, utc_now
from orchestration import digest
from security import DB, CurrentUser, InputModel, require_member

router = APIRouter()


class Decision(InputModel):
    payload_hash: str = Field(min_length=64, max_length=64)


@router.get("/workspaces/{workspace_id}/action-proposals")
def listing(workspace_id: str, user: CurrentUser, db: DB):
    require_member(db, user.id, workspace_id)
    return {
        "items": [
            proposal_out(db, row)
            for row in db.query(ActionProposal)
            .filter_by(workspace_id=workspace_id)
            .order_by(ActionProposal.created_at.desc(), ActionProposal.id)
            .limit(50)
        ]
    }


@router.post("/workspaces/{workspace_id}/action-proposals/{proposal_id}/{choice}")
def decide(
    workspace_id: str,
    proposal_id: str,
    choice: Literal["approve", "reject"],
    payload: Decision,
    user: CurrentUser,
    db: DB,
):
    lock_workspace(db, workspace_id, user.id, owner=True)
    row = db.query(ActionProposal).filter_by(workspace_id=workspace_id, id=proposal_id).first()
    if not row:
        raise HTTPException(404, "Action proposal not found")
    if row.state != "pending" or row.expires_at <= utc_now():
        raise HTTPException(409, "Proposal is no longer pending")
    if payload.payload_hash != row.payload_hash or digest(row.payload) != row.payload_hash:
        raise HTTPException(409, "Exact proposal payload hash does not match")
    if choice == "approve" and not visible(db, db.get(AgentRun, row.run_id)):
        raise HTTPException(409, "Source knowledge changed; request a new plan")
    row.state, row.approver_id, row.responded_at = (
        "approved" if choice == "approve" else "rejected",
        user.id,
        utc_now(),
    )
    db.commit()
    return proposal_out(db, row)
