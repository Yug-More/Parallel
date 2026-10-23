"""Explicit opt-in local index requests; membership checked independently of search."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from collaboration import lock_workspace
from embedding_providers import configured_provider
from knowledge_sources import fingerprint, resolve
from models import RetrievalIndex, Workspace, utc_now
from security import DB, CurrentUser, InputModel, require_member
from semantic import LocalNgrams, index_snapshot

router = APIRouter()


class IndexRequest(InputModel):
    provider: Literal["character", "trained"] = "character"
    external_consent: bool = False
    include_historical: bool = False


def out(row, epoch):
    return {
        "id": row.id,
        "state": row.state if row.epoch == epoch else "stale",
        "provider": row.provider,
        "model": row.model,
        "error_code": row.error_code,
        "passage_count": len(row.entries),
        "dimensions": row.dimensions,
        "duration_ms": row.duration_ms,
        "input_characters": row.input_characters,
        "usage_tokens": row.usage_tokens,
        "attempt": row.attempt,
        "options": row.options,
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
        "trained_enabled": request.app.state.settings.embedding_provider != "disabled",
        "external": request.app.state.settings.embedding_provider == "openai",
        "note": "Local character similarity, not a trained semantic model.",
        "items": [out(r, epoch) for r in rows],
    }


@router.post("/workspaces/{workspace_id}/retrieval-index", status_code=202)
def queue(
    workspace_id: str,
    user: CurrentUser,
    db: DB,
    request: Request,
    body: IndexRequest | None = None,
):
    body = body or IndexRequest()
    lock_workspace(db, workspace_id, user.id, owner=body.provider == "trained")
    settings = request.app.state.settings
    provider = configured_provider(settings) if body.provider == "trained" else LocalNgrams()
    if provider is None or (body.provider == "character" and not settings.local_index_enabled):
        raise HTTPException(503, "Optional local index is disabled")
    if getattr(provider, "external", False) and not body.external_consent:
        raise HTTPException(422, "Explicit external data transmission consent required")
    options = {
        "external_consent": body.external_consent,
        "include_historical": body.include_historical,
        "scope": "authorized_sources" if body.provider == "trained" else "current_documents",
    }
    if body.provider == "trained":
        options.update(
            maximum_sources=64,
            maximum_batch_size=16,
            maximum_calls=4,
            maximum_input_bytes=64000,
            maximum_source_bytes=2000,
        )
        try:
            _, options["source_fingerprint"] = index_snapshot(
                db, workspace_id, True, body.include_historical
            )
        except ValueError:
            raise HTTPException(
                409, "Trained index capacity is 64 authorized sources; narrow workspace scope"
            ) from None
    epoch = db.get(Workspace, workspace_id).knowledge_epoch
    previous = (
        db.query(RetrievalIndex)
        .filter_by(workspace_id=workspace_id, provider=provider.name, model=provider.model)
        .order_by(RetrievalIndex.created_at.desc())
        .first()
    )
    if (
        previous
        and previous.epoch == epoch
        and previous.state in {"queued", "running", "ready"}
        and previous.options == options
    ):
        if previous.state != "ready":
            return out(previous, epoch)
        try:
            unchanged = all(
                fingerprint(resolve(db, workspace_id, entry.get("kind", "document"), entry["id"]))
                == entry["fingerprint"]
                for entry in previous.entries
            )
        except Exception:
            unchanged = False
        if unchanged:
            return out(previous, epoch)
        previous.state, previous.entries = "cancelled", []
    if previous and (utc_now() - previous.created_at).total_seconds() < 60:
        raise HTTPException(429, "Wait one minute between indexing attempts")
    attempts_query = db.query(RetrievalIndex).filter_by(
        workspace_id=workspace_id, epoch=epoch, provider=provider.name, model=provider.model
    )
    if body.provider == "trained":
        # Native edits do not advance the revocable-knowledge epoch. A changed
        # source snapshot gets a new bounded attempt series, while the shared
        # minute quota and workspace cooldown still limit external spending.
        attempts_query = attempts_query.filter(
            RetrievalIndex.options["source_fingerprint"].as_string()
            == options["source_fingerprint"]
        )
    attempts = attempts_query.count()
    if attempts >= 3:
        raise HTTPException(429, "Three indexing attempts allowed per knowledge version")
    row = RetrievalIndex(
        id=str(uuid4()),
        workspace_id=workspace_id,
        creator_id=user.id,
        epoch=epoch,
        provider=provider.name,
        model=provider.model,
        state="queued",
        entries=[],
        options=options,
        attempt=attempts + 1,
    )
    db.add(row)
    db.commit()
    return out(row, epoch)
