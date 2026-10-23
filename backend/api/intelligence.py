"""Authorized source navigation, deterministic search and time-bounded briefings."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from collaboration import lock_workspace
from models import (
    Activity,
    Approval,
    Decision,
    DecisionRevision,
    Task,
    TaskDependency,
    WorkspaceVisit,
    utc_now,
)
from provenance import SourceKind, source_record
from retrieval import naive_utc, retrieve
from security import DB, CurrentUser, InputModel, as_utc, require_member

router = APIRouter()


@router.get("/workspaces/{workspace_id}/sources/{kind}/{source_id}")
def source(workspace_id: str, kind: SourceKind, source_id: str, user: CurrentUser, db: DB):
    require_member(db, user.id, workspace_id)
    return source_record(db, workspace_id, kind, source_id)


@router.get("/workspaces/{workspace_id}/knowledge")
def search(
    workspace_id: str,
    user: CurrentUser,
    db: DB,
    q: str = Query("", max_length=200),
    kind: SourceKind | None = None,
    status: str | None = Query(None, max_length=30),
    since: datetime | None = None,
    until: datetime | None = None,
    include_historical: bool = False,
    include_archived: bool = False,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
):
    require_member(db, user.id, workspace_id)
    start, end = naive_utc(since), naive_utc(until)
    if start and end and start > end:
        raise HTTPException(422, "Since must precede until")
    result = retrieve(
        db,
        workspace_id,
        q=q,
        kind=kind,
        status=status,
        since=start,
        until=end,
        include_historical=include_historical,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return {
        **result,
        "generated_at": as_utc(utc_now()),
        "synthesis": "Deterministic source results; no model interpretation was generated.",
    }


@router.get("/workspaces/{workspace_id}/continuity")
def briefing(
    workspace_id: str,
    user: CurrentUser,
    db: DB,
    since: datetime | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
):
    require_member(db, user.id, workspace_id)
    now = utc_now()
    visit = db.get(WorkspaceVisit, (workspace_id, user.id))
    start = naive_utc(since) if since else visit.through if visit else None
    if start and start > now:
        raise HTTPException(422, "Since cannot be in the future")
    events = db.query(Activity).filter(
        Activity.workspace_id == workspace_id, Activity.created_at <= now
    )
    revisions = db.query(DecisionRevision).filter(
        DecisionRevision.workspace_id == workspace_id, DecisionRevision.created_at <= now
    )
    if start:
        events = events.filter(Activity.created_at > start)
        revisions = revisions.filter(DecisionRevision.created_at > start)
    task_counts = dict(
        db.query(Task.status, func.count())
        .filter_by(workspace_id=workspace_id, archived=False)
        .group_by(Task.status)
        .all()
    )
    decision_counts = dict(
        db.query(Decision.status, func.count())
        .filter_by(workspace_id=workspace_id)
        .group_by(Decision.status)
        .all()
    )
    pending = db.query(Approval).filter(
        Approval.workspace_id == workspace_id,
        Approval.state == "pending",
        Approval.expires_at > now,
    )
    prerequisite = aliased(Task)
    unresolved = (
        select(TaskDependency.task_id)
        .join(prerequisite, prerequisite.id == TaskDependency.depends_on_id)
        .where(
            TaskDependency.workspace_id == workspace_id,
            or_(prerequisite.status != "done", prerequisite.archived.is_(True)),
        )
    )
    blockers = db.query(Task).filter(
        Task.workspace_id == workspace_id,
        Task.archived.is_(False),
        Task.status != "done",
        or_(Task.status == "blocked", Task.id.in_(unresolved)),
    )
    changes = retrieve(
        db,
        workspace_id,
        since=start,
        until=now,
        include_historical=True,
        include_archived=True,
        limit=limit,
        offset=offset,
    )
    return {
        "generated_at": as_utc(now),
        "since": as_utc(start),
        "first_visit": visit is None,
        "blocked_task_total": blockers.count(),
        "blocked_tasks": [
            source_record(db, workspace_id, "task", row.id)
            for row in blockers.order_by(Task.updated_at.desc(), Task.id)
            .offset(offset)
            .limit(limit)
        ],
        "task_counts": task_counts,
        "decision_counts": decision_counts,
        "pending_approvals": pending.count(),
        "changes": changes,
        "events": [
            {
                "id": row.id,
                "summary": row.summary,
                "actor_id": row.user_id,
                "actor_name": row.user_name,
                "event_at": as_utc(row.created_at),
                "kind": "activity",
            }
            for row in events.order_by(Activity.created_at.desc(), Activity.id)
            .offset(offset)
            .limit(limit)
        ],
        "event_total": events.count(),
        "decision_changes": [
            {
                "id": row.decision_id,
                "version": row.version,
                "reason": row.reason,
                "snapshot": row.snapshot,
                "event_at": as_utc(row.created_at),
            }
            for row in revisions.order_by(
                DecisionRevision.created_at.desc(), DecisionRevision.decision_id
            )
            .offset(offset)
            .limit(limit)
        ],
        "decision_change_total": revisions.count(),
        "note": "Current counts are live state; changes use event timestamps. Source text may conflict and is not automatically accepted as a decision.",
    }


class VisitInput(InputModel):
    through: datetime = Field()


@router.post("/workspaces/{workspace_id}/continuity/visit")
def visit(workspace_id: str, payload: VisitInput, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    through = naive_utc(payload.through)
    if through > utc_now():
        raise HTTPException(422, "Cannot mark future changes as seen")
    item = db.get(WorkspaceVisit, (workspace_id, user.id))
    if item is None:
        item = WorkspaceVisit(workspace_id=workspace_id, user_id=user.id, through=through)
        db.add(item)
    elif through > item.through:
        item.through = through
    db.commit()
    return {"through": as_utc(item.through)}
