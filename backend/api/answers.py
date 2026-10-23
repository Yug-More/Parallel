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
from retrieval import retrieve
from security import DB, CurrentUser, InputModel, require_member

router = APIRouter()


class Question(InputModel):
    question: str = Field(min_length=3, max_length=200)
    mode: Literal["extractive", "model"] = "extractive"
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
        if existing.question != payload.question or existing.mode != payload.mode:
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
    results = retrieve(db, workspace_id, q=payload.question, limit=8)
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
    row = KnowledgeAnswer(
        id=str(uuid4()),
        workspace_id=workspace_id,
        creator_id=user.id,
        question=payload.question,
        mode=payload.mode,
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
        request.app.state.auth_limiter.check("provider-global-budget", limit=30)
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
    try:
        current_evidence(db, row)
    except HTTPException:
        claims, code = [], "evidence_changed"
    row.claims, row.error_code = claims, code
    row.state = "failed" if code else "completed" if claims else "abstained"
    row.completed_at = utc_now()
    db.commit()
    return answer_out(db, row)
