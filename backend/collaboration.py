"""Transactional workspace mutations share one database serialization boundary."""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import update

from models import Activity, Invitation, Membership, Task, User, Workspace, utc_now
from security import require_member


def lock_workspace(db, workspace_id, user_id=None, owner=False):
    # UPDATE takes a row lock on PostgreSQL and a writer lock on SQLite. Acquire
    # before checking membership so a concurrent removal cannot authorize a write.
    result = db.execute(
        update(Workspace)
        .where(Workspace.id == workspace_id)
        .values(revision=Workspace.revision + 1)
    )
    if result.rowcount != 1:
        raise HTTPException(404, "Workspace not found")
    if user_id is not None:
        require_member(db, user_id, workspace_id, owner=owner)
    return db.get(Workspace, workspace_id, populate_existing=True)


def record_activity(db, workspace_id, actor, summary):
    db.add(
        Activity(
            id=str(uuid4()),
            workspace_id=workspace_id,
            user_id=actor.id,
            user_name=actor.name,
            summary=summary,
        )
    )


def remove_membership(db, workspace_id, target_id, actor):
    membership = db.get(Membership, (workspace_id, target_id))
    if membership is None:
        raise HTTPException(404, "Member not found")
    if membership.role == "owner":
        raise HTTPException(409, "Transfer ownership before removing or leaving as owner")
    tasks = (
        db.query(Task)
        .filter(Task.workspace_id == workspace_id, Task.assignee_id == target_id)
        .all()
    )
    for task in tasks:
        task.assignee_id = None
        task.version += 1
        task.updated_at = utc_now()
    db.query(Invitation).filter(
        Invitation.workspace_id == workspace_id,
        Invitation.recipient_id == target_id,
        Invitation.status == "pending",
    ).update({"status": "revoked", "responded_at": utc_now()})
    db.flush()  # clear composite assignment FKs before deleting membership
    db.delete(membership)
    record_activity(
        db,
        workspace_id,
        actor,
        f"Removed {db.get(User, target_id).name}; unassigned {len(tasks)} task(s)",
    )
