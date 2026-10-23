from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from collaboration import lock_workspace, record_activity, remove_membership
from models import Invitation, Membership, User, Workspace, utc_now
from security import DB, CurrentUser, InputModel, as_utc, require_member

router = APIRouter()


class WorkspaceInput(InputModel):
    name: str = Field(min_length=1, max_length=120)


class MemberInput(InputModel):
    email: str = Field(min_length=3, max_length=254)


def create_workspace(db, user, name):
    workspace = Workspace(id=str(uuid4()), name=name, owner_id=user.id)
    db.add(workspace)
    db.flush()
    db.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.flush()
    return workspace


def workspace_out(workspace, membership):
    return {
        "id": workspace.id,
        "name": workspace.name,
        "owner_id": workspace.owner_id,
        "role": membership.role,
        "created_at": as_utc(workspace.created_at),
    }


@router.get("/workspaces")
def list_workspaces(user: CurrentUser, db: DB):
    rows = (
        db.query(Workspace, Membership)
        .join(Membership)
        .filter(Membership.user_id == user.id)
        .order_by(Workspace.created_at, Workspace.id)
        .all()
    )
    return [workspace_out(workspace, membership) for workspace, membership in rows]


@router.post("/workspaces", status_code=201)
def new_workspace(payload: WorkspaceInput, user: CurrentUser, db: DB):
    workspace = create_workspace(db, user, payload.name)
    db.commit()
    return workspace_out(workspace, db.get(Membership, (workspace.id, user.id)))


@router.get("/workspaces/{workspace_id}")
def get_workspace(workspace_id: str, user: CurrentUser, db: DB):
    membership = require_member(db, user.id, workspace_id)
    return workspace_out(db.get(Workspace, workspace_id), membership)


@router.get("/workspaces/{workspace_id}/members")
def list_members(workspace_id: str, user: CurrentUser, db: DB):
    require_member(db, user.id, workspace_id)
    rows = (
        db.query(User, Membership)
        .join(Membership)
        .filter(Membership.workspace_id == workspace_id)
        .order_by(User.name)
        .all()
    )
    return [
        {"id": member.id, "name": member.name, "role": membership.role}
        for member, membership in rows
    ]


@router.post("/workspaces/{workspace_id}/members", status_code=201)
def add_member(workspace_id: str, payload: MemberInput, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id, owner=True)
    matches = db.query(User).filter(func.lower(User.email) == payload.email.lower()).all()
    if len(matches) != 1:
        raise HTTPException(404, "Account not available for membership")
    member = matches[0]
    if db.get(Membership, (workspace_id, member.id)):
        raise HTTPException(409, "Already a workspace member")
    db.add(Membership(workspace_id=workspace_id, user_id=member.id, role="member"))
    db.query(Invitation).filter(
        Invitation.workspace_id == workspace_id,
        Invitation.recipient_id == member.id,
        Invitation.status == "pending",
    ).update({"status": "revoked", "responded_at": utc_now()})
    record_activity(db, workspace_id, user, f"Added member {member.name}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Already a workspace member") from None
    return {"id": member.id, "name": member.name, "role": "member"}


class TransferInput(InputModel):
    user_id: str = Field(min_length=1, max_length=100)


@router.delete("/workspaces/{workspace_id}/members/{member_id}")
def remove_member(workspace_id: str, member_id: str, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id, owner=True)
    remove_membership(db, workspace_id, member_id, user)
    db.commit()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/leave")
def leave_workspace(workspace_id: str, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    remove_membership(db, workspace_id, user.id, user)
    db.commit()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/transfer-ownership")
def transfer_ownership(workspace_id: str, payload: TransferInput, user: CurrentUser, db: DB):
    workspace = lock_workspace(db, workspace_id, user.id, owner=True)
    if payload.user_id == user.id:
        raise HTTPException(409, "Already the workspace owner")
    target = db.get(Membership, (workspace_id, payload.user_id))
    if target is None:
        raise HTTPException(422, "New owner must be a current workspace member")
    current = db.get(Membership, (workspace_id, user.id))
    current.role = "member"
    db.flush()  # satisfy the unique owner index during this atomic transfer
    target.role = "owner"
    workspace.owner_id = payload.user_id
    db.query(Invitation).filter(
        Invitation.workspace_id == workspace_id, Invitation.status == "pending"
    ).update({"status": "revoked", "responded_at": utc_now()})
    record_activity(
        db, workspace_id, user, f"Transferred ownership to {db.get(User, payload.user_id).name}"
    )
    db.commit()
    return workspace_out(workspace, current)
