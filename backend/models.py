from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text
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
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class Membership(Base):
    __tablename__ = "workspace_memberships"
    workspace_id = Column(String, ForeignKey("workspaces.id"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True, index=True)
    role = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (CheckConstraint("role IN ('owner', 'member')", name="ck_membership_role"),)
