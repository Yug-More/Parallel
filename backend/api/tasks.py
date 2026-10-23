"""Persistent workspace tasks with optimistic versions and a small acyclic dependency graph."""

from datetime import date
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field, model_validator

from collaboration import lock_workspace, record_activity
from models import Membership, Task, TaskDependency, User, utc_now
from security import DB, CurrentUser, InputModel, as_utc, require_member

router = APIRouter()
Status = Literal["todo", "in_progress", "blocked", "done"]
Priority = Literal["low", "medium", "high", "urgent"]


class TaskInput(InputModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=12000)
    assignee_id: str | None = Field(default=None, max_length=100)
    status: Status = "todo"
    priority: Priority = "medium"
    due_date: date | None = None
    dependency_ids: list[str] = Field(default_factory=list, max_length=50)


class TaskEdit(InputModel):
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=12000)
    assignee_id: str | None = Field(default=None, max_length=100)
    status: Status | None = None
    priority: Priority | None = None
    due_date: date | None = None
    dependency_ids: list[str] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for name in ("title", "description", "status", "priority", "dependency_ids"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class VersionInput(InputModel):
    version: int = Field(ge=1)


def task_out(db, task):
    creator = db.get(User, task.creator_id)
    assignee = db.get(User, task.assignee_id) if task.assignee_id else None
    dependencies = (
        db.query(Task)
        .join(TaskDependency, TaskDependency.depends_on_id == Task.id)
        .filter(TaskDependency.workspace_id == task.workspace_id, TaskDependency.task_id == task.id)
        .order_by(Task.created_at, Task.id)
        .all()
    )
    return {
        "id": task.id,
        "workspace_id": task.workspace_id,
        "title": task.title,
        "description": task.description,
        "creator_id": creator.id,
        "creator_name": creator.name,
        "assignee_id": task.assignee_id,
        "assignee_name": assignee.name if assignee else None,
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date,
        "archived": task.archived,
        "version": task.version,
        "created_at": as_utc(task.created_at),
        "updated_at": as_utc(task.updated_at),
        "dependencies": [
            {"id": item.id, "title": item.title, "status": item.status} for item in dependencies
        ],
    }


def get_task(db, workspace_id, task_id):
    task = db.query(Task).filter_by(id=task_id, workspace_id=workspace_id).first()
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


def validate_assignment(db, workspace_id, assignee_id):
    if assignee_id is not None and db.get(Membership, (workspace_id, assignee_id)) is None:
        raise HTTPException(422, "Assignee must be a current workspace member")


def validate_dependencies(db, task, dependencies, status):
    ids = set(dependencies)
    if task.id in ids:
        raise HTTPException(422, "A task cannot depend on itself")
    prerequisites = (
        db.query(Task)
        .filter(Task.workspace_id == task.workspace_id, Task.id.in_(ids), Task.archived.is_(False))
        .all()
        if ids
        else []
    )
    if len(prerequisites) != len(ids):
        raise HTTPException(422, "Dependencies must be active tasks in this workspace")
    if status == "done" and any(item.status != "done" for item in prerequisites):
        raise HTTPException(409, "Complete prerequisite tasks before marking this task Done")
    edges = (
        db.query(TaskDependency)
        .filter(TaskDependency.workspace_id == task.workspace_id, TaskDependency.task_id != task.id)
        .all()
    )
    graph = {}
    for edge in edges:
        graph.setdefault(edge.task_id, set()).add(edge.depends_on_id)
    graph[task.id] = ids
    # Iterative reachability avoids recursion-depth failures on long task chains.
    pending, visited = list(ids), set()
    while pending:
        node = pending.pop()
        if node == task.id:
            raise HTTPException(409, "Task dependencies cannot contain a cycle")
        if node not in visited:
            visited.add(node)
            pending.extend(graph.get(node, ()))


def replace_dependencies(db, task, ids):
    db.query(TaskDependency).filter_by(workspace_id=task.workspace_id, task_id=task.id).delete()
    db.flush()
    for prerequisite_id in set(ids):
        db.add(
            TaskDependency(
                workspace_id=task.workspace_id, task_id=task.id, depends_on_id=prerequisite_id
            )
        )


@router.get("/workspaces/{workspace_id}/tasks")
def list_tasks(
    workspace_id: str,
    user: CurrentUser,
    db: DB,
    archived: bool = False,
    status: Status | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
):
    require_member(db, user.id, workspace_id)
    query = db.query(Task).filter_by(workspace_id=workspace_id, archived=archived)
    if status:
        query = query.filter(Task.status == status)
    total = query.count()
    rows = query.order_by(Task.created_at.desc(), Task.id.desc()).offset(offset).limit(limit).all()
    return {"items": [task_out(db, task) for task in rows], "total": total}


@router.get("/workspaces/{workspace_id}/tasks/{task_id}")
def task_detail(workspace_id: str, task_id: str, user: CurrentUser, db: DB):
    require_member(db, user.id, workspace_id)
    return task_out(db, get_task(db, workspace_id, task_id))


@router.post("/workspaces/{workspace_id}/tasks", status_code=201)
def create_task(workspace_id: str, payload: TaskInput, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    validate_assignment(db, workspace_id, payload.assignee_id)
    task = Task(
        id=str(uuid4()),
        workspace_id=workspace_id,
        creator_id=user.id,
        **payload.model_dump(exclude={"dependency_ids"}),
    )
    validate_dependencies(db, task, payload.dependency_ids, payload.status)
    db.add(task)
    db.flush()
    replace_dependencies(db, task, payload.dependency_ids)
    record_activity(db, workspace_id, user, f"Created task: {task.title}")
    db.commit()
    return task_out(db, task)


@router.patch("/workspaces/{workspace_id}/tasks/{task_id}")
def edit_task(workspace_id: str, task_id: str, payload: TaskEdit, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    task = get_task(db, workspace_id, task_id)
    if task.archived:
        raise HTTPException(409, "Archived tasks cannot be edited")
    if task.version != payload.version:
        raise HTTPException(409, "Task changed. Reload the latest version before editing.")
    changes = payload.model_dump(exclude_unset=True, exclude={"version", "dependency_ids"})
    if "assignee_id" in changes:
        validate_assignment(db, workspace_id, changes["assignee_id"])
    current_ids = {
        edge.depends_on_id
        for edge in db.query(TaskDependency).filter_by(workspace_id=workspace_id, task_id=task.id)
    }
    ids = set(payload.dependency_ids) if payload.dependency_ids is not None else current_ids
    status = changes.get("status", task.status)
    validate_dependencies(db, task, ids, status)
    if task.status == "done" and status != "done":
        done_dependent = (
            db.query(Task)
            .join(TaskDependency, TaskDependency.task_id == Task.id)
            .filter(
                TaskDependency.workspace_id == workspace_id,
                TaskDependency.depends_on_id == task.id,
                Task.status == "done",
                Task.archived.is_(False),
            )
            .first()
        )
        if done_dependent:
            raise HTTPException(409, "Reopen completed dependent tasks first")
    changed = (
        any(getattr(task, key) != value for key, value in changes.items()) or ids != current_ids
    )
    if changed:
        for key, value in changes.items():
            setattr(task, key, value)
        task.version += 1
        task.updated_at = utc_now()
        if ids != current_ids:
            replace_dependencies(db, task, ids)
        record_activity(db, workspace_id, user, f"Updated task: {task.title} ({task.status})")
    db.commit()
    return task_out(db, task)


@router.post("/workspaces/{workspace_id}/tasks/{task_id}/archive")
def archive_task(workspace_id: str, task_id: str, payload: VersionInput, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    task = get_task(db, workspace_id, task_id)
    if task.archived or task.version != payload.version:
        raise HTTPException(409, "Task changed or is already archived")
    dependent = (
        db.query(Task)
        .join(TaskDependency, TaskDependency.task_id == Task.id)
        .filter(
            TaskDependency.workspace_id == workspace_id,
            TaskDependency.depends_on_id == task.id,
            Task.archived.is_(False),
        )
        .first()
    )
    if dependent:
        raise HTTPException(409, "Remove active dependent links before archiving this prerequisite")
    replace_dependencies(db, task, [])
    task.archived = True
    task.version += 1
    task.updated_at = utc_now()
    record_activity(db, workspace_id, user, f"Archived task: {task.title}")
    db.commit()
    return task_out(db, task)
