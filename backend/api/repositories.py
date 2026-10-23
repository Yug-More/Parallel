"""Workspace owners explicitly authorize public read-only repository imports."""

import re
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from collaboration import lock_workspace, record_activity
from knowledge_lifecycle import advance
from models import RepositoryConnection, RepositorySync, utc_now
from repositories import connection_out
from security import DB, CurrentUser, InputModel, require_member

router = APIRouter()


class Connect(InputModel):
    repository: str = Field(min_length=3, max_length=200)


class Version(InputModel):
    version: int = Field(ge=1)


def connection(db, wid, cid):
    row = db.query(RepositoryConnection).filter_by(workspace_id=wid, id=cid).first()
    if not row:
        raise HTTPException(404, "Connection not found")
    return row


def queue(db, row, user):
    if not row.active:
        raise HTTPException(409, "Connection revoked")
    recent = (
        db.query(RepositorySync)
        .filter(
            RepositorySync.connection_id == row.id,
            RepositorySync.created_at > utc_now() - timedelta(minutes=5),
        )
        .first()
    )
    pending = (
        db.query(RepositorySync)
        .filter(
            RepositorySync.connection_id == row.id, RepositorySync.state.in_(["queued", "running"])
        )
        .first()
    )
    if pending:
        return
    if recent:
        raise HTTPException(429, "Wait five minutes between repository syncs")
    db.add(
        RepositorySync(
            id=str(uuid4()),
            workspace_id=row.workspace_id,
            connection_id=row.id,
            initiator_id=user.id,
            connection_version=row.version,
            state="queued",
            attempt=0,
            record_count=0,
        )
    )


@router.get("/workspaces/{workspace_id}/connections")
def listing(workspace_id: str, user: CurrentUser, db: DB, request: Request):
    require_member(db, user.id, workspace_id)
    return {
        "enabled": request.app.state.settings.github_connector_enabled,
        "private_enabled": request.app.state.settings.github_app_enabled,
        "items": [
            connection_out(db, row)
            for row in db.query(RepositoryConnection)
            .filter_by(workspace_id=workspace_id)
            .order_by(RepositoryConnection.created_at.desc())
            .limit(20)
        ],
    }


@router.post("/workspaces/{workspace_id}/connections", status_code=202)
def create(workspace_id: str, payload: Connect, user: CurrentUser, db: DB, request: Request):
    lock_workspace(db, workspace_id, user.id, owner=True)
    if not request.app.state.settings.github_connector_enabled:
        raise HTTPException(503, "Public GitHub connector is disabled by server configuration")
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", payload.repository
    ) or payload.repository.split("/")[1] in {".", ".."}:
        raise HTTPException(422, "Use owner/repository, not a URL")
    if db.query(RepositoryConnection).filter_by(workspace_id=workspace_id).count() >= 20:
        raise HTTPException(409, "Workspace connection limit reached")
    existing = (
        db.query(RepositoryConnection)
        .filter_by(workspace_id=workspace_id, repository=payload.repository, active=True)
        .first()
    )
    if existing:
        return connection_out(db, existing)
    row = RepositoryConnection(
        id=str(uuid4()),
        workspace_id=workspace_id,
        creator_id=user.id,
        repository=payload.repository,
        active=True,
        version=1,
    )
    db.add(row)
    db.flush()
    queue(db, row, user)
    record_activity(db, workspace_id, user, "Authorized a read-only public GitHub connection")
    db.commit()
    return connection_out(db, row)


@router.post("/workspaces/{workspace_id}/connections/{connection_id}/sync", status_code=202)
def sync(
    workspace_id: str,
    connection_id: str,
    payload: Version,
    user: CurrentUser,
    db: DB,
    request: Request,
):
    lock_workspace(db, workspace_id, user.id, owner=True)
    if not request.app.state.settings.github_connector_enabled:
        raise HTTPException(503, "Public GitHub connector is disabled by server configuration")
    row = connection(db, workspace_id, connection_id)
    if row.version != payload.version:
        raise HTTPException(409, "Connection changed; reload")
    queue(db, row, user)
    db.commit()
    return connection_out(db, row)


@router.post("/workspaces/{workspace_id}/connections/{connection_id}/revoke")
def revoke(workspace_id: str, connection_id: str, payload: Version, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id, owner=True)
    row = connection(db, workspace_id, connection_id)
    if row.version != payload.version:
        raise HTTPException(409, "Connection changed; reload")
    if row.active:
        advance(db, workspace_id)
        row.active, row.version = False, row.version + 1
        row.credential = row.credential_expires_at = row.access_verified_until = None
        db.query(RepositorySync).filter(
            RepositorySync.connection_id == row.id, RepositorySync.state.in_(["queued", "running"])
        ).update(
            {
                "state": "cancelled",
                "lease_token": None,
                "lease_until": None,
                "completed_at": utc_now(),
            }
        )
        record_activity(
            db, workspace_id, user, "Revoked GitHub connection; imports are unavailable"
        )
    db.commit()
    return connection_out(db, row)
