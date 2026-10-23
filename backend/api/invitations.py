"""In-app invitations are addressed to immutable registered account IDs, not bearer links."""

from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy import func

from collaboration import lock_workspace, record_activity
from models import Invitation, Membership, User, Workspace, utc_now
from security import DB, CurrentUser, InputModel, as_utc, require_member

router = APIRouter()


class InviteInput(InputModel):
    email: str = Field(min_length=3, max_length=254)
    expires_in_days: int = Field(default=7, ge=1, le=30)


def invitation_out(db, invitation):
    workspace = db.get(Workspace, invitation.workspace_id)
    recipient = db.get(User, invitation.recipient_id)
    inviter = db.get(User, invitation.inviter_id)
    status = invitation.status
    if status == "pending" and invitation.expires_at <= utc_now():
        status = "expired"
    return {
        "id": invitation.id,
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "recipient_id": recipient.id,
        "recipient_name": recipient.name,
        "inviter_name": inviter.name,
        "status": status,
        "created_at": as_utc(invitation.created_at),
        "expires_at": as_utc(invitation.expires_at),
    }


@router.get("/invitations")
def inbox(user: CurrentUser, db: DB):
    invitations = (
        db.query(Invitation)
        .filter(
            Invitation.recipient_id == user.id,
            Invitation.status == "pending",
            Invitation.expires_at > utc_now(),
        )
        .order_by(Invitation.created_at.desc())
        .limit(100)
        .all()
    )
    return [invitation_out(db, invitation) for invitation in invitations]


@router.get("/workspaces/{workspace_id}/invitations")
def sent(workspace_id: str, user: CurrentUser, db: DB):
    require_member(db, user.id, workspace_id, owner=True)
    invitations = (
        db.query(Invitation)
        .filter(Invitation.workspace_id == workspace_id)
        .order_by(Invitation.created_at.desc())
        .limit(100)
        .all()
    )
    return [invitation_out(db, invitation) for invitation in invitations]


@router.post("/workspaces/{workspace_id}/invitations", status_code=201)
def invite(workspace_id: str, payload: InviteInput, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id, owner=True)
    recipients = db.query(User).filter(func.lower(User.email) == payload.email.lower()).all()
    if len(recipients) != 1:
        raise HTTPException(404, "Invitations currently require an existing registered account")
    recipient = recipients[0]
    if db.get(Membership, (workspace_id, recipient.id)):
        raise HTTPException(409, "Account is already a workspace member")
    pending = (
        db.query(Invitation)
        .filter_by(workspace_id=workspace_id, recipient_id=recipient.id, status="pending")
        .first()
    )
    if pending:
        if pending.expires_at > utc_now():
            raise HTTPException(409, "An invitation is already pending")
        pending.status = "expired"
        pending.responded_at = utc_now()
        db.flush()
    invitation = Invitation(
        id=str(uuid4()),
        workspace_id=workspace_id,
        recipient_id=recipient.id,
        inviter_id=user.id,
        status="pending",
        expires_at=utc_now() + timedelta(days=payload.expires_in_days),
    )
    db.add(invitation)
    record_activity(db, workspace_id, user, f"Invited {recipient.name} in app")
    db.commit()
    return invitation_out(db, invitation)


def pending_invitation(db, invitation):
    if invitation.status != "pending":
        raise HTTPException(409, "Invitation is no longer pending")
    if invitation.expires_at <= utc_now():
        invitation.status = "expired"
        invitation.responded_at = utc_now()
        db.commit()
        raise HTTPException(410, "Invitation has expired")


@router.post("/invitations/{invitation_id}/{action}")
def respond(invitation_id: str, action: str, user: CurrentUser, db: DB):
    if action not in {"accept", "decline"}:
        raise HTTPException(404, "Action not found")
    invitation = db.query(Invitation).filter_by(id=invitation_id, recipient_id=user.id).first()
    if invitation is None:
        raise HTTPException(404, "Invitation not found")
    lock_workspace(db, invitation.workspace_id)
    db.refresh(invitation)
    pending_invitation(db, invitation)
    if action == "accept":
        if db.get(Membership, (invitation.workspace_id, user.id)):
            raise HTTPException(409, "Already a workspace member")
        db.add(Membership(workspace_id=invitation.workspace_id, user_id=user.id, role="member"))
        invitation.status = "accepted"
    else:
        invitation.status = "declined"
    invitation.responded_at = utc_now()
    record_activity(db, invitation.workspace_id, user, f"{invitation.status.title()} an invitation")
    db.commit()
    return invitation_out(db, invitation)


@router.post("/workspaces/{workspace_id}/invitations/{invitation_id}/revoke")
def revoke(workspace_id: str, invitation_id: str, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id, owner=True)
    invitation = db.query(Invitation).filter_by(id=invitation_id, workspace_id=workspace_id).first()
    if invitation is None:
        raise HTTPException(404, "Invitation not found")
    pending_invitation(db, invitation)
    invitation.status = "revoked"
    invitation.responded_at = utc_now()
    record_activity(db, workspace_id, user, "Revoked an invitation")
    db.commit()
    return invitation_out(db, invitation)
