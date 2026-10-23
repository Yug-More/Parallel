"""Source resolution always stays inside an already authorized workspace.

Source text is data, never an instruction or an authorization decision. Snapshots
preserve what a decision cited; live previews show subsequent corrections.
"""

from typing import Literal

from fastapi import HTTPException
from pydantic import Field

from models import Activity, Decision, DecisionRevision, DecisionSource, Message, Task, User
from security import InputModel, as_utc

SourceKind = Literal["message", "task", "activity", "decision"]
FIELDS = ("title", "context", "statement", "rationale", "alternatives", "tradeoffs", "status")
MODELS = {"message": Message, "task": Task, "activity": Activity, "decision": Decision}


class SourceRef(InputModel):
    kind: SourceKind
    id: str = Field(min_length=1, max_length=100)


def iso(value):
    return as_utc(value).isoformat() if value else None


def source_record(db, workspace_id, kind, source_id):
    model = MODELS.get(kind)
    row = (
        db.query(model).filter_by(workspace_id=workspace_id, id=source_id).first()
        if model
        else None
    )
    if row is None:
        raise HTTPException(404, "Source not found in this workspace")
    if kind == "decision":
        title = row.title
        body = "\n\n".join(f"{key.title()}: {getattr(row, key)}" for key in FIELDS[1:6])
    elif kind == "task":
        title, body = row.title, row.description
    elif kind == "message":
        title, body = f"Message from {row.sender_name}", row.content
    else:
        title, body = row.summary[:200], row.summary
    return {
        "kind": kind,
        "id": row.id,
        "workspace_id": workspace_id,
        "title": title,
        "body": body,
        "status": getattr(row, "status", None),
        "version": getattr(row, "version", None),
        "archived": getattr(row, "archived", False),
        "created_at": iso(row.created_at),
        "updated_at": iso(getattr(row, "updated_at", row.created_at)),
        "authority": "interpretation"
        if kind == "message" and row.role == "assistant"
        else "source_record",
        "superseded_by_id": getattr(row, "superseded_by_id", None),
    }


def validate_sources(db, workspace_id, refs, decision_id=None):
    result = []
    seen = set()
    for ref in refs:
        if (ref.kind, ref.id) in seen:
            raise HTTPException(422, "Duplicate source reference")
        seen.add((ref.kind, ref.id))
        if ref.kind == "decision" and ref.id == decision_id:
            raise HTTPException(422, "A decision cannot cite itself")
        result.append(source_record(db, workspace_id, ref.kind, ref.id))
    return result


def snapshot_decision(decision):
    return {
        **{key: getattr(decision, key) for key in FIELDS},
        "superseded_by_id": decision.superseded_by_id,
    }


def save_revision(db, decision, actor_id, reason, sources):
    db.add(
        DecisionRevision(
            workspace_id=decision.workspace_id,
            decision_id=decision.id,
            version=decision.version,
            actor_id=actor_id,
            reason=reason,
            snapshot=snapshot_decision(decision),
            created_at=decision.updated_at,
        )
    )
    db.flush()
    for source in sources:
        # Store bounded source evidence as it existed at this revision, independently
        # of later edits. The full original remains navigable through its stable ID.
        snapshot = {**source, "body": source["body"][:2000]}
        db.add(
            DecisionSource(
                workspace_id=decision.workspace_id,
                decision_id=decision.id,
                revision=decision.version,
                kind=source["kind"],
                source_id=source["id"],
                snapshot=snapshot,
            )
        )


def revision_sources(db, decision, version=None):
    return (
        db.query(DecisionSource)
        .filter_by(
            workspace_id=decision.workspace_id,
            decision_id=decision.id,
            revision=version or decision.version,
        )
        .order_by(DecisionSource.kind, DecisionSource.source_id)
        .all()
    )


def decision_out(db, decision):
    creator = db.get(User, decision.creator_id)
    return {
        "id": decision.id,
        "workspace_id": decision.workspace_id,
        **snapshot_decision(decision),
        "version": decision.version,
        "creator_id": decision.creator_id,
        "creator_name": creator.name,
        "created_at": as_utc(decision.created_at),
        "updated_at": as_utc(decision.updated_at),
        "sources": [
            {
                "cited": source.snapshot,
                "current": source_record(db, decision.workspace_id, source.kind, source.source_id),
            }
            for source in revision_sources(db, decision)
        ],
    }
