"""Evidence-bound answer validation and revocation-safe reads."""

import re
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
        "retrieval_mode": answer.retrieval_mode,
        "evidence_plan": answer.evidence_plan,
        "provider_model": answer.provider_model,
        "state": state,
        "claims": claims,
        "evidence": evidence,
        "error_code": answer.error_code,
        "created_at": as_utc(answer.created_at),
        "warnings": evidence_warnings(evidence),
        "note": "Source excerpts are untrusted quotations."
        if answer.mode == "extractive"
        else "Model interpretation. Citation IDs were validated; factual correctness and entailment were not automatically proven.",
    }


def evidence_warnings(evidence):
    """Conservative lexical conflict hints, never a truth/entailment detector."""
    warnings = ["Evidence may be incomplete; inspect cited sources."] if evidence else []
    if any(
        s.get("status") in {"historical", "superseded", "rejected"}
        or s.get("kind") == "decision_revision"
        for s in evidence
    ):
        warnings.append("Historical evidence is included; check the current decision.")
    for i, left in enumerate(evidence):
        a = set(re.findall(r"\w+", left["body"].casefold())) - {
            "the",
            "a",
            "and",
            "is",
            "to",
            "of",
            "in",
        }
        for right in evidence[i + 1 :]:
            b = set(re.findall(r"\w+", right["body"].casefold())) - {
                "the",
                "a",
                "and",
                "is",
                "to",
                "of",
                "in",
            }
            negation = {"not", "never", "no", "disabled", "forbidden"}
            if len((a & b) - negation) >= 3 and bool(a & negation) != bool(b & negation):
                warnings.append(
                    "Potential conflicting wording: inspect both sources; no resolution was inferred."
                )
                return warnings
    return warnings


def planned_evidence(db, workspace_id, question):
    """Bounded explicit question intents; all other questions stay lexical.

    No inference changes task state, resolves disagreement, or asserts completion.
    """
    from retrieval import retrieve

    result = retrieve(db, workspace_id, q=question, limit=8)
    plan = {"strategy": "lexical", "scope": "current authorized sources"}
    terms = set(re.findall(r"\w+", question.casefold()))
    special = []
    if terms & {"blocker", "blockers", "blocked", "blocking"}:
        special = retrieve(db, workspace_id, q="", kind="task", status="blocked", limit=8)["items"]
        plan = {
            "strategy": "explicit_blocked_tasks_then_lexical",
            "scope": "current tasks explicitly marked blocked; this does not detect every implicit blocker",
        }
    elif {"what", "changed"} <= terms:
        special = retrieve(
            db, workspace_id, q="", kind="activity", since=utc_now() - timedelta(days=1), limit=8
        )["items"]
        plan = {
            "strategy": "recent_activity_then_lexical",
            "scope": "recorded workspace activity in the last 24 hours; external work may be missing",
        }
    seen, rows = set(), []
    for row in [*special, *result["items"]]:
        if row["ref"] not in seen:
            rows.append(row)
            seen.add(row["ref"])
    return {**result, "items": rows[:8]}, plan
