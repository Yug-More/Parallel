"""Bounded UTF-8 document extraction using durable database leases.

Raw uploads are discarded after terminal processing. Archived documents cannot
be retrieved, including historical passages. No document text is executable.
"""

import hashlib
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException

from collaboration import lock_workspace
from models import Document, DocumentPassage, DocumentRevision, Membership, utc_now
from provenance import iso

MAX_BYTES = 512 * 1024
MAX_CHARACTERS = 200_000


def document_out(db, document):
    revisions = (
        db.query(DocumentRevision)
        .filter_by(document_id=document.id)
        .order_by(DocumentRevision.version.desc())
        .all()
    )
    return {
        "id": document.id,
        "title": document.title,
        "filename": document.filename,
        "version": document.version,
        "archived": document.archived,
        "created_at": iso(document.created_at),
        "updated_at": iso(document.updated_at),
        "revisions": [
            {
                "id": r.id,
                "filename": r.filename,
                "title": r.title,
                "creator_id": r.creator_id,
                "version": r.version,
                "state": r.state,
                "error_code": r.error_code,
                "content_hash": r.content_hash,
                "created_at": iso(r.created_at),
                "completed_at": iso(r.completed_at),
            }
            for r in revisions
        ],
    }


def passage_record(db, workspace_id, passage_id):
    row = (
        db.query(DocumentPassage, DocumentRevision, Document)
        .join(DocumentRevision, DocumentRevision.id == DocumentPassage.revision_id)
        .join(Document, Document.id == DocumentRevision.document_id)
        .filter(
            DocumentPassage.id == passage_id,
            DocumentPassage.workspace_id == workspace_id,
            Document.archived.is_(False),
            DocumentRevision.state == "ready",
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Source not found in this workspace")
    passage, revision, document = row
    return {
        "id": passage.id,
        "kind": "document",
        "workspace_id": workspace_id,
        "title": revision.title,
        "body": passage.body,
        "version": revision.version,
        "status": "current" if revision.version == document.version else "historical",
        "archived": False,
        "created_at": iso(passage.created_at),
        "updated_at": iso(passage.created_at),
        "authority": "untrusted_document",
        "document_id": document.id,
        "revision_id": revision.id,
        "ordinal": passage.ordinal,
        "page_number": passage.page_number,
        "filename": revision.filename,
    }


def extract_text(raw):
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text or any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise ValueError("binary_content")
    if len(text) > MAX_CHARACTERS:
        raise ValueError("text_limit")
    if not text.strip():
        raise ValueError("empty_document")
    return text


def ingest_once(factory, extract_fn=extract_text):
    now = utc_now()
    with factory() as db:
        expired = (
            db.query(DocumentRevision)
            .filter(DocumentRevision.state == "processing", DocumentRevision.lease_until < now)
            .order_by(DocumentRevision.created_at)
            .first()
        )
        if expired:
            lock_workspace(db, expired.workspace_id)
            db.refresh(expired)
            if expired.state == "processing" and expired.lease_until < utc_now():
                expired.state, expired.error_code = "failed", "lease_expired"
                expired.raw_content = expired.lease_token = expired.lease_until = None
                expired.completed_at = utc_now()
            db.commit()
            return True
        revision = (
            db.query(DocumentRevision)
            .filter_by(state="queued")
            .order_by(DocumentRevision.created_at, DocumentRevision.id)
            .first()
        )
        if not revision:
            return False
        lock_workspace(db, revision.workspace_id)
        db.refresh(revision)
        if revision.state != "queued":
            return True
        document = db.get(Document, revision.document_id)
        if document.archived or not db.get(
            Membership, (document.workspace_id, revision.creator_id)
        ):
            revision.state = "cancelled"
            revision.raw_content = None
            revision.completed_at = utc_now()
            db.commit()
            return True
        token = str(uuid4())
        revision.state, revision.lease_token = "processing", token
        revision.lease_until = now + timedelta(seconds=30)
        raw, revision_id, workspace_id = revision.raw_content, revision.id, revision.workspace_id
        is_pdf = revision.filename.lower().endswith(".pdf")
        db.commit()
    error = None
    try:
        if is_pdf:
            from pdf_extract import extract_pdf

            pages = extract_pdf(raw)
        else:
            pages = [(None, extract_fn(raw))]
    except UnicodeDecodeError:
        error = "invalid_utf8"
    except ValueError as exc:
        error = (
            str(exc)
            if str(exc)
            in {
                "binary_content",
                "text_limit",
                "empty_document",
                "pdf_invalid",
                "pdf_encrypted",
                "pdf_page_limit",
                "pdf_timeout",
                "pdf_resource_limit",
                "pdf_no_text",
            }
            else "extraction_failed"
        )
    except Exception:
        error = "extraction_failed"
    with factory() as db:
        lock_workspace(db, workspace_id)
        revision = db.get(DocumentRevision, revision_id)
        if revision.state != "processing" or revision.lease_token != token:
            return True
        document = db.get(Document, revision.document_id)
        if revision.lease_until < utc_now():
            error = "lease_expired"
        cancelled = document.archived or not db.get(Membership, (workspace_id, revision.creator_id))
        if not cancelled and not error:
            from segmentation import segments

            for ordinal, (page_number, body) in enumerate(
                (page, part) for page, text in pages for part in segments(text)
            ):
                db.add(
                    DocumentPassage(
                        id=str(uuid5(NAMESPACE_URL, f"parallel:document:{revision.id}:{ordinal}")),
                        workspace_id=workspace_id,
                        revision_id=revision.id,
                        ordinal=ordinal,
                        title=revision.title,
                        body=body,
                        page_number=page_number,
                    )
                )
        revision.state = "cancelled" if cancelled else "failed" if error else "ready"
        revision.error_code = error
        revision.completed_at = utc_now()
        revision.raw_content = revision.lease_token = revision.lease_until = None
        db.commit()
    return True


def content_hash(raw):
    return hashlib.sha256(raw).hexdigest()
