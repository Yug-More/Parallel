"""Deterministic SQL lexical retrieval. No embeddings or generated answers.

Title term matches score 3, body matches 1; a complete title phrase adds 4.
Terms are OR candidates. Ties sort by event time, kind and immutable ID.
"""

import math
import re
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import String, case, cast, func, literal, or_, select, union_all

from models import (
    Activity,
    Decision,
    DecisionRevision,
    Document,
    DocumentPassage,
    DocumentRevision,
    ImportedRecord,
    Message,
    RepositoryConnection,
    Task,
    Workspace,
)
from provenance import iso


def naive_utc(value):
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(422, "Timestamps must include a timezone")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def pattern(value):
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def retrieve(
    db,
    workspace_id,
    *,
    q="",
    kind=None,
    status=None,
    since=None,
    until=None,
    include_historical=False,
    include_archived=False,
    limit=20,
    offset=0,
    ranking="coverage",
):
    terms = list(dict.fromkeys(re.findall(r"\w+", q.lower())))[:12]
    if ranking not in {"legacy", "coverage", "focused"}:
        raise ValueError("unsupported_ranking")
    if ranking in {"coverage", "focused"}:
        stopwords = {
            "a",
            "an",
            "the",
            "is",
            "are",
            "was",
            "were",
            "what",
            "which",
            "how",
            "why",
            "of",
            "for",
            "to",
            "in",
            "on",
            "and",
            "with",
        }
        if ranking == "focused":
            stopwords.update({"do", "does", "we", "our", "please", "tell", "me"})
        terms = [term for term in terms if term not in stopwords]
        # Stopword-only questions abstain rather than treating an empty query as all records.
        if q.strip() and not terms:
            return {
                "items": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "method": "deterministic_lexical_v2",
                "evidence": "no_matching_evidence",
            }
    branches = []
    configs = [
        (
            Decision,
            "decision",
            Decision.title,
            Decision.context
            + " "
            + Decision.statement
            + " "
            + Decision.rationale
            + " "
            + Decision.alternatives
            + " "
            + Decision.tradeoffs,
            Decision.updated_at,
            Decision.status,
            Decision.version,
            literal(False),
            literal("structured_fact"),
        ),
        (
            Task,
            "task",
            Task.title,
            Task.description,
            Task.updated_at,
            Task.status,
            Task.version,
            Task.archived,
            literal("structured_fact"),
        ),
        (
            Message,
            "message",
            literal("Message from ") + Message.sender_name,
            Message.content,
            Message.created_at,
            Message.role,
            literal(None, type_=String),
            literal(False),
            case((Message.role == "assistant", "interpretation"), else_="raw_source"),
        ),
        (
            Activity,
            "activity",
            func.substr(Activity.summary, 1, 200),
            Activity.summary,
            Activity.created_at,
            literal("event"),
            literal(None, type_=String),
            literal(False),
            literal("event_record"),
        ),
        (
            DocumentPassage,
            "document",
            DocumentPassage.title,
            DocumentPassage.body,
            DocumentPassage.created_at,
            case((DocumentRevision.version == Document.version, "current"), else_="historical"),
            DocumentRevision.version,
            literal(False),
            literal("untrusted_document"),
        ),
        (
            ImportedRecord,
            "external",
            ImportedRecord.title,
            ImportedRecord.body,
            ImportedRecord.updated_at,
            ImportedRecord.status,
            ImportedRecord.version,
            literal(False),
            literal("untrusted_import"),
        ),
    ]
    if include_historical or kind == "decision_revision":
        configs.append(
            (
                DecisionRevision,
                "decision_revision",
                DecisionRevision.snapshot["title"].as_string(),
                DecisionRevision.snapshot["context"].as_string()
                + " "
                + DecisionRevision.snapshot["statement"].as_string()
                + " "
                + DecisionRevision.snapshot["rationale"].as_string()
                + " "
                + DecisionRevision.snapshot["alternatives"].as_string()
                + " "
                + DecisionRevision.snapshot["tradeoffs"].as_string(),
                DecisionRevision.created_at,
                DecisionRevision.snapshot["status"].as_string(),
                DecisionRevision.version,
                literal(False),
                literal("historical_decision_revision"),
            )
        )
    for model, name, title, body, event_at, state, version, archived, authority in configs:
        if kind and name != kind:
            continue
        stmt = select(
            (
                DecisionRevision.decision_id + "@" + cast(DecisionRevision.version, String)
                if name == "decision_revision"
                else model.id
            ).label("id"),
            literal(name).label("kind"),
            title.label("title"),
            func.substr(body, 1, 2000).label("excerpt"),
            event_at.label("event_at"),
            state.label("status"),
            cast(version, String).label("version"),
            archived.label("archived"),
            authority.label("authority"),
        )
        if name == "document":
            stmt = stmt.join(
                DocumentRevision, DocumentRevision.id == DocumentPassage.revision_id
            ).join(Document, Document.id == DocumentRevision.document_id)
        if name == "decision_revision":
            stmt = stmt.join(Decision, Decision.id == DecisionRevision.decision_id)
        if name == "external":
            stmt = stmt.join(
                RepositoryConnection, RepositoryConnection.id == ImportedRecord.connection_id
            )
        conditions = [model.workspace_id == workspace_id]
        if name == "decision_revision":
            conditions.append(DecisionRevision.version < Decision.version)
        if name == "message":
            epoch = db.get(Workspace, workspace_id).knowledge_epoch
            conditions.append(
                or_(Message.knowledge_epoch.is_(None), Message.knowledge_epoch == epoch)
            )
        if name == "external":
            conditions.extend(
                [RepositoryConnection.active.is_(True), ImportedRecord.available.is_(True)]
            )
        if name == "document":
            # Archive is a revocation boundary, including explicit history/archive searches.
            conditions.extend([Document.archived.is_(False), DocumentRevision.state == "ready"])
            if not include_historical:
                conditions.append(DocumentRevision.version == Document.version)
        if name == "decision" and not include_historical:
            conditions.append(Decision.status.in_(["proposed", "accepted"]))
        if name == "task" and not include_archived:
            conditions.append(Task.archived.is_(False))
        if status:
            conditions.append(state == status)
        if since:
            conditions.append(event_at > since)
        if until:
            conditions.append(event_at <= until)
        score = literal(0)
        matches = []
        coverage = literal(0)
        for term in terms:
            title_match = func.lower(title).like(pattern(term), escape="\\")
            body_match = func.lower(body).like(pattern(term), escape="\\")
            matches.extend([title_match, body_match])
            coverage = coverage + case((or_(title_match, body_match), 1), else_=0)
            score = score + case((title_match, 3), else_=0) + case((body_match, 1), else_=0)
        if terms:
            score = score + case(
                (func.lower(title).like(pattern(q.lower()), escape="\\"), 4), else_=0
            )
            conditions.append(
                coverage >= math.ceil(len(terms) * 0.6)
                if ranking in {"coverage", "focused"}
                else or_(*matches)
            )
        if ranking == "focused" and terms:
            phrase = " ".join(terms)
            score = score + case((func.lower(body).like(pattern(phrase), escape="\\"), 2), else_=0)
            if name == "decision":
                score = score + case((Decision.status == "accepted", 2), else_=0)
            if name == "document":
                score = score + case((DocumentRevision.version == Document.version, 1), else_=0)
        branches.append(stmt.add_columns(score.label("score")).where(*conditions))
    combined = union_all(*branches).subquery()
    total = db.execute(select(func.count()).select_from(combined)).scalar()
    rows = db.execute(
        select(combined)
        .order_by(
            combined.c.score.desc(), combined.c.event_at.desc(), combined.c.kind, combined.c.id
        )
        .offset(offset)
        .limit(limit)
    ).mappings()
    return {
        "items": [
            {
                **dict(row),
                "event_at": iso(row["event_at"]),
                "version": int(row["version"]) if row["version"] else None,
                "ref": f"{row['kind']}:{row['id']}",
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "method": "deterministic_lexical_v3"
        if ranking == "focused"
        else "deterministic_lexical_v2"
        if ranking == "coverage"
        else "deterministic_lexical_v1",
        "evidence": "matching_sources" if total else "no_matching_evidence",
    }
