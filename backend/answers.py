"""Evidence-bound answer validation and revocation-safe reads."""

from datetime import timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import Field

from knowledge_sources import fingerprint, resolve
from models import utc_now
from security import InputModel, as_utc


class Claim(InputModel):
    text: str = Field(min_length=1, max_length=1500)
    kind: Literal["fact", "inference"]
    citations: list[str] = Field(min_length=1, max_length=8)


class Claims(InputModel):
    claims: list[Claim] = Field(max_length=8)


def validate_claims(value, evidence):
    parsed = Claims.model_validate(value)
    allowed = {item["ref"] for item in evidence}
    if any(not set(claim.citations) <= allowed for claim in parsed.claims):
        raise ValueError("invalid_citation")
    return [claim.model_dump() for claim in parsed.claims]


def current_evidence(db, answer):
    result = []
    for ref in answer.evidence:
        source = resolve(db, answer.workspace_id, ref["kind"], ref["id"])
        if fingerprint(source) != ref["fingerprint"]:
            raise HTTPException(409, "Answer evidence changed")
        result.append({**source, "body": source["body"][:1500], "ref": ref["ref"]})
    return result


def answer_out(db, answer):
    state, claims, evidence = answer.state, answer.claims, []
    if answer.state == "processing" and answer.created_at < utc_now() - timedelta(minutes=2):
        state = "interrupted"
    try:
        evidence = current_evidence(db, answer)
    except HTTPException:
        state, claims = "evidence_unavailable", []
    return {
        "id": answer.id,
        "question": answer.question,
        "mode": answer.mode,
        "provider_model": answer.provider_model,
        "state": state,
        "claims": claims,
        "evidence": evidence,
        "error_code": answer.error_code,
        "created_at": as_utc(answer.created_at),
        "note": "Source excerpts are untrusted quotations."
        if answer.mode == "extractive"
        else "Model interpretation. Citation IDs were validated; factual correctness and entailment were not automatically proven.",
    }
