"""Explicit opt-in local index requests; membership checked independently of search."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from collaboration import lock_workspace
from models import RetrievalIndex, Workspace, utc_now
from security import DB, CurrentUser, require_member
from semantic import LocalNgrams

router = APIRouter()


def out(row, epoch):
    return {
        "id": row.id,
        "state": row.state if row.epoch == epoch else "stale",
        "provider": row.provider,
        "model": row.model,
        "error_code": row.error_code,
        "passage_count": len(row.entries),
    }


@router.get("/workspaces/{workspace_id}/retrieval-index")
def status(workspace_id: str, user: CurrentUser, db: DB, request: Request):
    require_member(db, user.id, workspace_id)
    epoch = db.get(Workspace, workspace_id).knowledge_epoch
    rows = (
        db.query(RetrievalIndex)
        .filter_by(workspace_id=workspace_id)
        .order_by(RetrievalIndex.created_at.desc())
        .limit(5)
        .all()
    )
    return {
        "enabled": request.app.state.settings.local_index_enabled,
        "note": "Local character similarity, not a trained semantic model.",
        "items": [out(r, epoch) for r in rows],
    }


@router.post("/workspaces/{workspace_id}/retrieval-index", status_code=202)
def queue(workspace_id: str, user: CurrentUser, db: DB, request: Request):
    lock_workspace(db, workspace_id, user.id)
    if not request.app.state.settings.local_index_enabled:
        raise HTTPException(503, "Optional local index is disabled")
    epoch = db.get(Workspace, workspace_id).knowledge_epoch
    previous = (
        db.query(RetrievalIndex)
        .filter_by(workspace_id=workspace_id)
        .order_by(RetrievalIndex.created_at.desc())
        .first()
    )
    if previous and previous.epoch == epoch and previous.state in {"queued", "running", "ready"}:
        return out(previous, epoch)
    if previous and (utc_now() - previous.created_at).total_seconds() < 60:
        raise HTTPException(429, "Wait one minute between indexing attempts")
    provider = LocalNgrams()
    row = RetrievalIndex(
        id=str(uuid4()),
        workspace_id=workspace_id,
        creator_id=user.id,
        epoch=epoch,
        provider=provider.name,
        model=provider.model,
        state="queued",
        entries=[],
    )
    db.add(row)
    db.commit()
    return out(row, epoch)
