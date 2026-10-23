"""Owner-only, exact-previewed retention actions. Never automatic on migration."""

import hashlib
import hmac
import json
import time
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from collaboration import lock_workspace
from models import Document, Membership, RepositoryConnection, RetentionReceipt
from retention import counts, redact
from security import DB, CurrentUser, InputModel

router = APIRouter()


class Scope(InputModel):
    scope: Literal["derived", "document", "connection", "close"]
    target_id: str | None = Field(None, max_length=100)


class Confirmation(Scope):
    expected_revision: int = Field(ge=0)
    expires: int
    plan_hash: str = Field(min_length=64, max_length=64)
    confirmation: Literal["ERASE REVIEWED CONTENT"]


def owner_lock(db, wid, uid):
    workspace = lock_workspace(db, wid)
    membership = db.get(Membership, (wid, uid))
    if not membership:
        raise HTTPException(404, "Workspace not found")
    if membership.role != "owner":
        raise HTTPException(403, "Workspace owner required")
    return workspace


def plan_for(db, workspace, user_id, scope, target_id, revision, expires):
    if workspace.closed_at:
        raise HTTPException(409, "Workspace is closed; retained audit receipts remain available")
    if scope in {"document", "connection"}:
        model = Document if scope == "document" else RepositoryConnection
        if not db.query(model).filter_by(workspace_id=workspace.id, id=target_id).first():
            raise HTTPException(404, "Retention target not found")
    elif target_id is not None:
        raise HTTPException(422, "This scope has no target ID")
    return {
        "workspace_id": workspace.id,
        "actor_id": user_id,
        "scope": scope,
        "target_id": target_id,
        "expected_revision": revision,
        "expires": expires,
        "epoch": workspace.knowledge_epoch,
        "workspace_counts": counts(db, workspace.id),
        "effects": "Erase all workspace derived context, reports, saved claims and vectors; cancel pending runs and approvals. Selected source scope additionally erases all its retained content versions. Closure erases all document/import content and denies workspace access.",
        "exceptions": "Human-authored messages, task and decision history, user-authored questions/objectives, native approved tasks, IDs, content hashes, approval hashes and execution receipts remain. Backups and external provider retention require separate operator handling.",
    }


def signature(plan, settings):
    return hmac.new(
        settings.secret_key.encode(), json.dumps(plan, sort_keys=True).encode(), hashlib.sha256
    ).hexdigest()


@router.post("/workspaces/{workspace_id}/retention/preview")
def preview(workspace_id: str, payload: Scope, user: CurrentUser, db: DB, request: Request):
    workspace = owner_lock(db, workspace_id, user.id)
    plan = plan_for(
        db,
        workspace,
        user.id,
        payload.scope,
        payload.target_id,
        workspace.revision,
        int(time.time()) + 300,
    )
    digest = signature(plan, request.app.state.settings)
    db.commit()
    return {**plan, "plan_hash": digest}


@router.post("/workspaces/{workspace_id}/retention/execute")
def execute(workspace_id: str, payload: Confirmation, user: CurrentUser, db: DB, request: Request):
    workspace = owner_lock(db, workspace_id, user.id)
    if (
        workspace.revision != payload.expected_revision + 1
        or not time.time() < payload.expires <= time.time() + 300
    ):
        raise HTTPException(409, "Retention preview expired or workspace changed; review again")
    plan = plan_for(
        db,
        workspace,
        user.id,
        payload.scope,
        payload.target_id,
        payload.expected_revision,
        payload.expires,
    )
    if not hmac.compare_digest(signature(plan, request.app.state.settings), payload.plan_hash):
        raise HTTPException(409, "Retention plan does not match the reviewed content")
    redact(db, workspace, payload.scope, payload.target_id)
    row = RetentionReceipt(
        id=str(uuid4()),
        workspace_id=workspace_id,
        actor_id=user.id,
        plan=plan,
        plan_hash=payload.plan_hash,
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "scope": payload.scope, "state": "completed", "plan_hash": row.plan_hash}


@router.get("/workspaces/{workspace_id}/retention/receipts")
def receipts(workspace_id: str, user: CurrentUser, db: DB):
    # This narrow owner-only audit route also works after closure.
    membership = db.get(Membership, (workspace_id, user.id))
    if not membership or membership.role != "owner":
        raise HTTPException(404, "Workspace not found")
    return {
        "items": [
            {
                "id": row.id,
                "plan": row.plan,
                "plan_hash": row.plan_hash,
                "created_at": row.created_at,
            }
            for row in db.query(RetentionReceipt)
            .filter_by(workspace_id=workspace_id)
            .order_by(RetentionReceipt.created_at.desc())
            .limit(50)
        ]
    }
