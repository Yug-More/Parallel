"""Versioned human decision records. Every correction has an immutable revision."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from collaboration import lock_workspace, record_activity
from models import Decision, DecisionRevision, utc_now
from provenance import (
    FIELDS,
    SourceRef,
    decision_out,
    revision_sources,
    save_revision,
    source_preview,
    validate_sources,
)
from security import DB, CurrentUser, InputModel, as_utc, require_member

router = APIRouter()
DecisionStatus = Literal["proposed", "accepted", "rejected", "superseded"]


class DecisionInput(InputModel):
    title: str = Field(min_length=1, max_length=200)
    context: str = Field(default="", max_length=6000)
    statement: str = Field(min_length=1, max_length=6000)
    rationale: str = Field(default="", max_length=6000)
    alternatives: str = Field(default="", max_length=6000)
    tradeoffs: str = Field(default="", max_length=6000)
    sources: list[SourceRef] = Field(default_factory=list, max_length=30)
    status: Literal["proposed", "accepted"] = "proposed"


class DecisionEdit(DecisionInput):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    status: Literal["proposed", "accepted", "rejected"] = "proposed"


class SupersedeInput(InputModel):
    version: int = Field(ge=1)
    successor_id: str = Field(min_length=1, max_length=100)
    successor_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


def get_decision(db, workspace_id, decision_id):
    item = db.query(Decision).filter_by(workspace_id=workspace_id, id=decision_id).first()
    if not item:
        raise HTTPException(404, "Decision not found")
    return item


@router.get("/workspaces/{workspace_id}/decisions")
def list_decisions(
    workspace_id: str,
    user: CurrentUser,
    db: DB,
    status: DecisionStatus | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
):
    require_member(db, user.id, workspace_id)
    query = db.query(Decision).filter_by(workspace_id=workspace_id)
    if status:
        query = query.filter_by(status=status)
    total = query.count()
    rows = query.order_by(Decision.updated_at.desc(), Decision.id).offset(offset).limit(limit).all()
    return {"items": [decision_out(db, row) for row in rows], "total": total}


@router.post("/workspaces/{workspace_id}/decisions", status_code=201)
def create_decision(workspace_id: str, payload: DecisionInput, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    sources = validate_sources(db, workspace_id, payload.sources)
    item = Decision(
        id=str(uuid4()),
        workspace_id=workspace_id,
        creator_id=user.id,
        version=1,
        **payload.model_dump(exclude={"sources"}),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(item)
    db.flush()
    save_revision(db, item, user.id, "Created decision", sources)
    record_activity(db, workspace_id, user, f"Recorded decision: {item.title} ({item.status})")
    db.commit()
    return decision_out(db, item)


@router.get("/workspaces/{workspace_id}/decisions/{decision_id}")
def detail(workspace_id: str, decision_id: str, user: CurrentUser, db: DB):
    require_member(db, user.id, workspace_id)
    return decision_out(db, get_decision(db, workspace_id, decision_id))


@router.get("/workspaces/{workspace_id}/decisions/{decision_id}/history")
def history(
    workspace_id: str,
    decision_id: str,
    user: CurrentUser,
    db: DB,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
):
    require_member(db, user.id, workspace_id)
    decision = get_decision(db, workspace_id, decision_id)
    query = db.query(DecisionRevision).filter_by(workspace_id=workspace_id, decision_id=decision_id)
    return {
        "total": query.count(),
        "items": [
            {
                "version": row.version,
                "reason": row.reason,
                "actor_id": row.actor_id,
                "created_at": as_utc(row.created_at),
                "snapshot": row.snapshot,
                "sources": [
                    source_preview(db, workspace_id, source)["cited"]
                    for source in revision_sources(db, decision, row.version)
                ],
            }
            for row in query.order_by(DecisionRevision.version.desc()).offset(offset).limit(limit)
        ],
    }


@router.patch("/workspaces/{workspace_id}/decisions/{decision_id}")
def revise(workspace_id: str, decision_id: str, payload: DecisionEdit, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    item = get_decision(db, workspace_id, decision_id)
    if item.version != payload.version:
        raise HTTPException(409, "Decision changed. Reload before saving.")
    if item.status in {"superseded", "rejected"}:
        raise HTTPException(409, "Terminal decisions are immutable; record a new decision")
    if item.status == "accepted" and payload.status != "accepted":
        raise HTTPException(409, "Accepted decisions can only be corrected or superseded")
    sources = validate_sources(db, workspace_id, payload.sources, item.id)
    old_refs = {(source.kind, source.source_id) for source in revision_sources(db, item)}
    changed = any(getattr(item, key) != getattr(payload, key) for key in FIELDS) or old_refs != {
        (s["kind"], s["id"]) for s in sources
    }
    if changed:
        for key in FIELDS:
            setattr(item, key, getattr(payload, key))
        item.version += 1
        item.updated_at = utc_now()
        save_revision(db, item, user.id, payload.reason, sources)
        record_activity(
            db,
            workspace_id,
            user,
            f"Revised decision: {item.title} (v{item.version}, {item.status})",
        )
    db.commit()
    return decision_out(db, item)


@router.post("/workspaces/{workspace_id}/decisions/{decision_id}/supersede")
def supersede(
    workspace_id: str, decision_id: str, payload: SupersedeInput, user: CurrentUser, db: DB
):
    lock_workspace(db, workspace_id, user.id)
    item = get_decision(db, workspace_id, decision_id)
    successor = get_decision(db, workspace_id, payload.successor_id)
    if item.id == successor.id or item.status != "accepted" or successor.status != "accepted":
        raise HTTPException(409, "Supersession requires two distinct current accepted decisions")
    if item.version != payload.version or successor.version != payload.successor_version:
        raise HTTPException(409, "Decision changed. Reload both decisions.")
    sources = [source.snapshot for source in revision_sources(db, item)]
    item.status, item.superseded_by_id = "superseded", successor.id
    item.version += 1
    item.updated_at = utc_now()
    save_revision(db, item, user.id, payload.reason, sources)
    record_activity(
        db, workspace_id, user, f"Superseded decision: {item.title} → {successor.title}"
    )
    db.commit()
    return decision_out(db, item)
