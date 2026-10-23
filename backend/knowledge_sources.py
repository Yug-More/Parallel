"""Authorized caller's unified source resolver and content fingerprints."""

import hashlib
import json

from documents import passage_record
from provenance import source_record
from repositories import external_record


def resolve(db, workspace_id, kind, source_id):
    if kind == "decision_revision":
        return revision_record(db, workspace_id, source_id)
    if kind == "document":
        return passage_record(db, workspace_id, source_id)
    if kind == "external":
        return external_record(db, workspace_id, source_id)
    return source_record(db, workspace_id, kind, source_id)


def fingerprint(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()


def revision_record(db, workspace_id, source_id):
    from fastapi import HTTPException

    from models import Decision, DecisionRevision
    from provenance import FIELDS, iso

    decision_id, separator, version = source_id.rpartition("@")
    if not separator or not version.isdigit() or len(version) > 9 or int(version) < 1:
        raise HTTPException(404, "Decision revision not found")
    row = (
        db.query(DecisionRevision)
        .filter_by(workspace_id=workspace_id, decision_id=decision_id, version=int(version))
        .first()
    )
    if not row:
        raise HTTPException(404, "Decision revision not found")
    decision = db.query(Decision).filter_by(workspace_id=workspace_id, id=decision_id).one()
    return {
        "kind": "decision_revision",
        "id": source_id,
        "workspace_id": workspace_id,
        "title": row.snapshot["title"],
        "body": "\n\n".join(f"{key.title()}: {row.snapshot[key]}" for key in FIELDS[1:6]),
        "status": row.snapshot["status"],
        "version": row.version,
        "archived": False,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.created_at),
        "authority": "historical_decision_revision",
        "decision_id": decision_id,
        "current_version": decision.version,
        "reason": row.reason,
    }
