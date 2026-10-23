"""Authorize, retrieve, bound, generate, validate, reauthorize, persist."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

import providers
from answers import answer_out, current_evidence, validate_claims
from collaboration import lock_workspace
from knowledge_sources import fingerprint, resolve
from models import KnowledgeAnswer, utc_now
from security import DB, CurrentUser, InputModel, require_member

router = APIRouter()


class Question(InputModel):
    question: str = Field(min_length=3, max_length=200)
    mode: Literal["extractive", "model"] = "extractive"
    retrieval_mode: Literal["lexical", "trained"] = "lexical"
    external_consent: bool = False
    idempotency_key: str = Field(min_length=8, max_length=100)


@router.get("/workspaces/{workspace_id}/answers")
def listing(workspace_id: str, user: CurrentUser, db: DB, request: Request):
    require_member(db, user.id, workspace_id)
    return {
        "model_enabled": bool(
            request.app.state.settings.grounded_model_enabled
            and request.app.state.settings.openai_api_key
        ),
        "items": [
            answer_out(db, row)
            for row in db.query(KnowledgeAnswer)
            .filter_by(workspace_id=workspace_id)
            .order_by(KnowledgeAnswer.created_at.desc(), KnowledgeAnswer.id)
            .limit(20)
        ],
    }


@router.post("/workspaces/{workspace_id}/answers", status_code=201)
def answer(workspace_id: str, payload: Question, user: CurrentUser, db: DB, request: Request):
    lock_workspace(db, workspace_id, user.id)
    existing = (
        db.query(KnowledgeAnswer)
        .filter_by(
            workspace_id=workspace_id, creator_id=user.id, idempotency_key=payload.idempotency_key
        )
        .first()
    )
    if existing:
        if (
            existing.question != payload.question
            or existing.mode != payload.mode
            or existing.retrieval_mode != payload.retrieval_mode
        ):
            raise HTTPException(409, "Idempotency key already used for another question")
        return answer_out(db, existing)
    settings = request.app.state.settings
    if payload.mode == "model" and not (
        settings.grounded_model_enabled and settings.openai_api_key
    ):
        raise HTTPException(503, "Grounded model answers are disabled; use source excerpts")
    if (
        db.query(KnowledgeAnswer)
        .filter(
            KnowledgeAnswer.workspace_id == workspace_id,
            KnowledgeAnswer.created_at > utc_now().replace(second=0, microsecond=0),
        )
        .count()
        >= 10
    ):
        raise HTTPException(429, "Answer request limit reached; wait a minute")
    from answers import planned_evidence

    results, evidence_plan = planned_evidence(db, workspace_id, payload.question)
    if payload.retrieval_mode == "trained":
        from embedding_providers import configured_provider
        from github_app import require_fresh_private_access
        from semantic import hybrid

        provider = configured_provider(settings)
        if provider is None:
            raise HTTPException(503, "Trained embedding provider is disabled")
        if provider.external:
            require_member(db, user.id, workspace_id, owner=True)
            require_fresh_private_access(db, workspace_id)
            if not payload.external_consent:
                raise HTTPException(422, "Explicit external query transmission consent required")
            db.commit()
            request.app.state.auth_limiter.check("embedding-global-budget", limit=12)
        results = hybrid(
            db, workspace_id, q=payload.question, provider=provider, user_id=user.id, limit=8
        )
        lock_workspace(db, workspace_id, user.id)
        # Trained retrieval releases the lock across latency. A competing request
        # may have completed this same idempotency key in the meantime.
        existing = (
            db.query(KnowledgeAnswer)
            .filter_by(
                workspace_id=workspace_id,
                creator_id=user.id,
                idempotency_key=payload.idempotency_key,
            )
            .first()
        )
        if existing:
            if (
                existing.question != payload.question
                or existing.mode != payload.mode
                or existing.retrieval_mode != payload.retrieval_mode
            ):
                raise HTTPException(409, "Idempotency key already used for another question")
            return answer_out(db, existing)
        evidence_plan = {
            "strategy": results["method"],
            "index_status": results["index_status"],
            "scope": "current authorized sources",
        }

    evidence = []
    refs = []
    for row in results["items"]:
        source = resolve(db, workspace_id, row["kind"], row["id"])
        ref = f"{source['kind']}:{source['id']}"
        refs.append(
            {
                "kind": source["kind"],
                "id": source["id"],
                "ref": ref,
                "fingerprint": fingerprint(source),
            }
        )
        evidence.append(
            {
                "ref": ref,
                "title": source["title"],
                "body": source["body"][:1500],
                "authority": source["authority"],
                "status": source["status"],
            }
        )
    if payload.mode == "model":
        from github_app import require_fresh_private_access

        require_fresh_private_access(db, workspace_id)
    row = KnowledgeAnswer(
        id=str(uuid4()),
        workspace_id=workspace_id,
        creator_id=user.id,
        question=payload.question,
        mode=payload.mode,
        retrieval_mode=payload.retrieval_mode,
        evidence_plan=evidence_plan,
        provider_model=settings.openai_model if payload.mode == "model" else None,
        idempotency_key=payload.idempotency_key,
        state="processing",
        claims=[],
        evidence=refs,
    )
    db.add(row)
    db.commit()  # provider latency never holds the workspace lock
    code = None
    if payload.mode == "model":
        try:
            request.app.state.auth_limiter.check("provider-global-budget", limit=30)
        except HTTPException:
            lock_workspace(db, workspace_id, user.id)
            db.refresh(row)
            if row.state == "processing":
                row.state, row.error_code, row.completed_at = "failed", "provider_budget", utc_now()
            db.commit()
            raise
    try:
        if not evidence:
            claims = []
        elif payload.mode == "extractive":
            claims = [
                {"text": item["body"] or item["title"], "kind": "fact", "citations": [item["ref"]]}
                for item in evidence
            ]
        else:
            claims = validate_claims(
                providers.generate_grounded(settings, payload.question, evidence), evidence
            )
    except Exception:
        claims, code = [], "answer_generation_failed"
    lock_workspace(db, workspace_id, user.id)
    db.refresh(row)
    if row.state != "processing":
        return answer_out(db, row)
    try:
        current_evidence(db, row)
    except HTTPException:
        claims, code = [], "evidence_changed"
    row.claims, row.error_code = claims, code
    row.state = "failed" if code else "completed" if claims else "abstained"
    row.completed_at = utc_now()
    db.commit()
    return answer_out(db, row)
