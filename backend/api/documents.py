"""Workspace-authorized local uploads. Filenames are metadata, never paths."""

import base64
import binascii
import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from collaboration import lock_workspace, record_activity
from documents import MAX_BYTES, content_hash, document_out, passage_record
from knowledge_lifecycle import advance
from models import Document, DocumentRevision, utc_now
from security import DB, CurrentUser, InputModel, require_member

router = APIRouter()


class Upload(InputModel):
    filename: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=700000)
    version: int | None = Field(None, ge=1)


class Version(InputModel):
    version: int = Field(ge=1)


def get_document(db, workspace_id, document_id):
    item = db.query(Document).filter_by(workspace_id=workspace_id, id=document_id).first()
    if not item:
        raise HTTPException(404, "Document not found")
    return item


def upload(db, workspace_id, payload, user, document_id=None):
    lock_workspace(db, workspace_id, user.id)
    filename = payload.filename
    if re.search(r"[/\\\x00-\x1f\x7f]", filename) or not filename.lower().endswith(
        (".txt", ".md", ".pdf")
    ):
        raise HTTPException(422, "Use a plain filename ending in .txt, .md or .pdf")
    try:
        raw = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Invalid base64 content") from None
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(422, "Upload must contain 1–524288 bytes")
    if filename.lower().endswith(".pdf") != raw.startswith(b"%PDF-"):
        raise HTTPException(422, "PDF content must match its filename and PDF signature")
    digest = content_hash(raw)
    if document_id:
        item = get_document(db, workspace_id, document_id)
        if item.archived or payload.version != item.version:
            raise HTTPException(409, "Document changed or archived; reload before revising")
        current = (
            db.query(DocumentRevision).filter_by(document_id=item.id, version=item.version).one()
        )
        if current.content_hash == digest and current.state not in {"failed", "cancelled"}:
            db.rollback()
            return document_out(db, item)
        if item.version >= 50:
            raise HTTPException(409, "Document revision limit reached")
        item.version += 1
        item.filename, item.title, item.updated_at = filename, payload.title, utc_now()
    else:
        if payload.version is not None:
            raise HTTPException(422, "Version is only used when revising a document")
        duplicate = (
            db.query(Document)
            .join(DocumentRevision, DocumentRevision.document_id == Document.id)
            .filter(
                Document.workspace_id == workspace_id,
                Document.archived.is_(False),
                DocumentRevision.version == Document.version,
                DocumentRevision.content_hash == digest,
                DocumentRevision.state.in_(["queued", "processing", "ready"]),
            )
            .first()
        )
        if duplicate:
            db.rollback()
            return document_out(db, duplicate)
        if db.query(Document).filter_by(workspace_id=workspace_id).count() >= 200:
            raise HTTPException(409, "Workspace document limit reached")
        item = Document(
            id=str(uuid4()),
            workspace_id=workspace_id,
            creator_id=user.id,
            filename=filename,
            title=payload.title,
            version=1,
        )
        db.add(item)
        db.flush()
    if (
        db.query(DocumentRevision)
        .filter(
            DocumentRevision.workspace_id == workspace_id,
            DocumentRevision.state.in_(["queued", "processing"]),
        )
        .count()
        >= 20
    ):
        raise HTTPException(409, "Document queue is full; wait for processing")
    db.add(
        DocumentRevision(
            id=str(uuid4()),
            workspace_id=workspace_id,
            document_id=item.id,
            creator_id=user.id,
            filename=filename,
            title=payload.title,
            version=item.version,
            content_hash=digest,
            state="queued",
            raw_content=raw,
        )
    )
    advance(db, workspace_id)
    record_activity(db, workspace_id, user, "Queued a document revision for local extraction")
    db.commit()
    return document_out(db, item)


@router.get("/workspaces/{workspace_id}/documents")
def listing(
    workspace_id: str,
    user: CurrentUser,
    db: DB,
    offset: int = Query(0, ge=0, le=10000),
    limit: int = Query(20, ge=1, le=50),
):
    require_member(db, user.id, workspace_id)
    query = db.query(Document).filter_by(workspace_id=workspace_id)
    return {
        "total": query.count(),
        "items": [
            document_out(db, row)
            for row in query.order_by(Document.created_at.desc(), Document.id)
            .offset(offset)
            .limit(limit)
        ],
    }


@router.post("/workspaces/{workspace_id}/documents", status_code=202)
def create(workspace_id: str, payload: Upload, user: CurrentUser, db: DB):
    return upload(db, workspace_id, payload, user)


@router.post("/workspaces/{workspace_id}/documents/{document_id}/revisions", status_code=202)
def revise(workspace_id: str, document_id: str, payload: Upload, user: CurrentUser, db: DB):
    return upload(db, workspace_id, payload, user, document_id)


@router.post("/workspaces/{workspace_id}/documents/{document_id}/archive")
def archive(workspace_id: str, document_id: str, payload: Version, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    item = get_document(db, workspace_id, document_id)
    if item.version != payload.version:
        raise HTTPException(409, "Document changed; reload before archiving")
    if not item.archived:
        advance(db, workspace_id)
        item.archived, item.updated_at, item.version = True, utc_now(), item.version + 1
        db.query(DocumentRevision).filter(
            DocumentRevision.document_id == item.id,
            DocumentRevision.state.in_(["queued", "processing"]),
        ).update(
            {
                "state": "cancelled",
                "raw_content": None,
                "lease_token": None,
                "lease_until": None,
                "completed_at": utc_now(),
            }
        )
        record_activity(db, workspace_id, user, "Archived a document; passages are unavailable")
    db.commit()
    return document_out(db, item)


@router.get("/workspaces/{workspace_id}/document-passages/{passage_id}")
def passage(workspace_id: str, passage_id: str, user: CurrentUser, db: DB):
    require_member(db, user.id, workspace_id)
    return passage_record(db, workspace_id, passage_id)
