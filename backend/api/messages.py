from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import and_, or_

import providers
from collaboration import lock_workspace
from models import Activity, Message, Workspace
from security import DB, CurrentUser, InputModel, as_utc, require_member

router = APIRouter()


class MessageInput(InputModel):
    content: str = Field(min_length=1, max_length=16000)


class ReplyInput(InputModel):
    message_id: str = Field(min_length=1, max_length=100)


def message_out(message, epoch=None):
    return {
        "id": message.id,
        "workspace_id": message.workspace_id,
        "sender_id": message.sender_id,
        "sender_name": message.sender_name,
        "role": message.role,
        "content": (
            message.content
            if message.knowledge_epoch is None or message.knowledge_epoch == epoch
            else "[Report hidden: source knowledge changed or became unavailable.]"
        ),
        "created_at": as_utc(message.created_at),
    }


def recent_context(db, workspace_id):
    rows = (
        db.query(Message)
        .filter(
            Message.workspace_id == workspace_id,
            or_(
                Message.knowledge_epoch.is_(None),
                Message.knowledge_epoch == db.get(Workspace, workspace_id).knowledge_epoch,
            ),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(30)
        .all()
    )
    return [
        {"role": message.role, "content": f"{message.sender_name}: {message.content[:2000]}"}
        for message in reversed(rows)
    ]


@router.get("/workspaces/{workspace_id}/messages")
def list_messages(
    workspace_id: str,
    user: CurrentUser,
    db: DB,
    limit: int = Query(50, ge=1, le=100),
    before: str | None = Query(None, max_length=100),
):
    require_member(db, user.id, workspace_id)
    query = db.query(Message).filter(Message.workspace_id == workspace_id)
    if before:
        cursor = query.filter(Message.id == before).first()
        if cursor is None:
            raise HTTPException(400, "Invalid message cursor")
        query = query.filter(
            or_(
                Message.created_at < cursor.created_at,
                and_(Message.created_at == cursor.created_at, Message.id < cursor.id),
            )
        )
    rows = query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit).all()
    return [
        message_out(message, db.get(Workspace, workspace_id).knowledge_epoch)
        for message in reversed(rows)
    ]


@router.post("/workspaces/{workspace_id}/messages", status_code=201)
def post_message(workspace_id: str, payload: MessageInput, user: CurrentUser, db: DB):
    lock_workspace(db, workspace_id, user.id)
    message = Message(
        id=str(uuid4()),
        workspace_id=workspace_id,
        user_id=user.id,
        sender_id=f"user:{user.id}",
        sender_name=user.name,
        role="user",
        content=payload.content,
    )
    db.add(message)
    db.add(
        Activity(
            id=str(uuid4()),
            workspace_id=workspace_id,
            user_id=user.id,
            user_name=user.name,
            summary="Posted a message",
        )
    )
    db.commit()
    return message_out(message)


@router.post("/workspaces/{workspace_id}/agent-replies", status_code=201)
def agent_reply(
    workspace_id: str, payload: ReplyInput, request: Request, user: CurrentUser, db: DB
):
    require_member(db, user.id, workspace_id)
    from github_app import require_fresh_private_access

    require_fresh_private_access(db, workspace_id)
    source = (
        db.query(Message)
        .filter(
            Message.id == payload.message_id,
            Message.workspace_id == workspace_id,
            Message.role == "user",
        )
        .first()
    )
    if source is None:
        raise HTTPException(404, "Source message not found")
    knowledge_epoch = db.get(Workspace, workspace_id).knowledge_epoch
    context = recent_context(db, workspace_id)
    db.rollback()
    request.app.state.auth_limiter.check("provider-global-budget", limit=30)
    try:
        answer = providers.generate_reply(request.app.state.settings, context)
    except providers.ProviderUnavailable:
        raise HTTPException(503, "AI is not configured. Your message is saved.") from None
    except providers.ProviderFailure:
        raise HTTPException(
            502, "AI provider failed. Your message is saved; no reply was created."
        ) from None
    db.rollback()  # end the read snapshot before re-authorizing the completed result
    workspace = lock_workspace(db, workspace_id, user.id)
    if workspace.knowledge_epoch != knowledge_epoch:
        raise HTTPException(
            409, "Source knowledge changed during generation; request a fresh reply"
        )
    message = Message(
        id=str(uuid4()),
        workspace_id=workspace_id,
        user_id=user.id,
        knowledge_epoch=knowledge_epoch,
        sender_id=f"agent:{user.id}",
        sender_name=f"{user.name}'s Agent",
        role="assistant",
        content=answer,
    )
    db.add(message)
    db.commit()
    return message_out(message, knowledge_epoch)


@router.get("/workspaces/{workspace_id}/activity")
def activity(workspace_id: str, user: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=100)):
    require_member(db, user.id, workspace_id)
    rows = (
        db.query(Activity)
        .filter(Activity.workspace_id == workspace_id)
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "user_id": row.user_id,
            "user_name": row.user_name,
            "summary": row.summary,
            "created_at": as_utc(row.created_at),
        }
        for row in rows
    ]
