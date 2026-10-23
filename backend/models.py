from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import relationship

from database import Base


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    last_seen_at = Column(DateTime, default=utc_now)

    credentials = relationship("UserCredential", back_populates="user", uselist=False)


class UserCredential(Base):
    __tablename__ = "user_credentials"
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", back_populates="credentials")


class Message(Base):
    """Workspace message; user_id preserves the original human/agent owner."""

    __tablename__ = "messages"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    sender_id = Column(String, nullable=False)
    sender_name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now, index=True)
    __table_args__ = (Index("ix_messages_workspace_created", "workspace_id", "created_at", "id"),)


class Activity(Base):
    """Workspace-scoped activity, attributed to an immutable user ID."""

    __tablename__ = "activities"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    user_name = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now, index=True)
    __table_args__ = (Index("ix_activities_workspace_created", "workspace_id", "created_at"),)


class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(String, primary_key=True)
    name = Column(String(120), nullable=False)
    revision = Column(Integer, nullable=False, server_default="0")
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class Membership(Base):
    __tablename__ = "workspace_memberships"
    workspace_id = Column(String, ForeignKey("workspaces.id"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True, index=True)
    role = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'member')", name="ck_membership_role"),
        Index(
            "uq_workspace_one_owner",
            "workspace_id",
            unique=True,
            sqlite_where=text("role='owner'"),
            postgresql_where=text("role='owner'"),
        ),
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id = Column(String(64), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime)


class Invitation(Base):
    __tablename__ = "workspace_invitations"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    recipient_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    inviter_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    responded_at = Column(DateTime)
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','accepted','declined','revoked','expired')",
            name="ck_invitation_status",
        ),
        Index(
            "uq_invitation_pending",
            "workspace_id",
            "recipient_id",
            unique=True,
            sqlite_where=text("status='pending'"),
            postgresql_where=text("status='pending'"),
        ),
    )


class Task(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    creator_id = Column(String, ForeignKey("users.id"), nullable=False)
    assignee_id = Column(String, nullable=True)
    status = Column(String(16), nullable=False, default="todo")
    priority = Column(String(16), nullable=False, default="medium")
    due_date = Column(Date, nullable=True)
    archived = Column(Boolean, nullable=False, server_default=false())
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_tasks_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "assignee_id"],
            ["workspace_memberships.workspace_id", "workspace_memberships.user_id"],
            name="fk_tasks_assignee_membership",
        ),
        CheckConstraint("status IN ('todo','in_progress','blocked','done')", name="ck_task_status"),
        CheckConstraint("priority IN ('low','medium','high','urgent')", name="ck_task_priority"),
        CheckConstraint("version >= 1", name="ck_task_version"),
        Index("ix_tasks_workspace_created", "workspace_id", "created_at", "id"),
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    workspace_id = Column(String, primary_key=True)
    task_id = Column(String, primary_key=True)
    depends_on_id = Column(String, primary_key=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["tasks.workspace_id", "tasks.id"],
            name="fk_dependency_task",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "depends_on_id"],
            ["tasks.workspace_id", "tasks.id"],
            name="fk_dependency_prerequisite",
        ),
        CheckConstraint("task_id <> depends_on_id", name="ck_dependency_not_self"),
        Index("ix_dependency_prerequisite", "workspace_id", "depends_on_id"),
    )
