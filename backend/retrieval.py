"""Deterministic SQL lexical retrieval. No embeddings or generated answers.

Title term matches score 3, body matches 1; a complete title phrase adds 4.
Terms are OR candidates. Ties sort by event time, kind and immutable ID.
"""

import re
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import String, case, cast, func, literal, or_, select, union_all

from models import Activity, Decision, Message, Task
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
):
    terms = list(dict.fromkeys(re.findall(r"\w+", q.lower())))[:12]
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
    ]
    for model, name, title, body, event_at, state, version, archived, authority in configs:
        if kind and name != kind:
            continue
        stmt = select(
            model.id.label("id"),
            literal(name).label("kind"),
            title.label("title"),
            func.substr(body, 1, 2000).label("excerpt"),
            event_at.label("event_at"),
            state.label("status"),
            cast(version, String).label("version"),
            archived.label("archived"),
            authority.label("authority"),
        )
        conditions = [model.workspace_id == workspace_id]
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
        for term in terms:
            title_match = func.lower(title).like(pattern(term), escape="\\")
            body_match = func.lower(body).like(pattern(term), escape="\\")
            matches.extend([title_match, body_match])
            score = score + case((title_match, 3), else_=0) + case((body_match, 1), else_=0)
        if terms:
            score = score + case(
                (func.lower(title).like(pattern(q.lower()), escape="\\"), 4), else_=0
            )
            conditions.append(or_(*matches))
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
        "method": "deterministic_lexical_v1",
        "evidence": "matching_sources" if total else "no_matching_evidence",
    }
