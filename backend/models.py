from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
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
    knowledge_epoch = Column(Integer)
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
    knowledge_epoch = Column(Integer, nullable=False, server_default="0")
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


class Decision(Base):
    __tablename__ = "decisions"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    title = Column(String(200), nullable=False)
    context = Column(Text, nullable=False)
    statement = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    alternatives = Column(Text, nullable=False)
    tradeoffs = Column(Text, nullable=False)
    status = Column(String(16), nullable=False)
    creator_id = Column(String, ForeignKey("users.id"), nullable=False)
    version = Column(Integer, nullable=False)
    superseded_by_id = Column(String)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_decision_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "superseded_by_id"],
            ["decisions.workspace_id", "decisions.id"],
            name="fk_decision_successor",
        ),
        CheckConstraint(
            "status IN ('proposed','accepted','superseded','rejected')", name="ck_decision_status"
        ),
        CheckConstraint("version >= 1", name="ck_decision_version"),
        CheckConstraint(
            "superseded_by_id IS NULL OR (superseded_by_id <> id AND status='superseded')",
            name="ck_decision_successor",
        ),
        Index("ix_decisions_workspace_updated", "workspace_id", "updated_at", "id"),
    )


class DecisionRevision(Base):
    __tablename__ = "decision_revisions"
    decision_id = Column(String, primary_key=True)
    version = Column(Integer, primary_key=True)
    workspace_id = Column(String, nullable=False)
    actor_id = Column(String, ForeignKey("users.id"), nullable=False)
    reason = Column(String(1000), nullable=False)
    snapshot = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (
        UniqueConstraint("workspace_id", "decision_id", "version", name="uq_revision_workspace"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_id"],
            ["decisions.workspace_id", "decisions.id"],
            name="fk_revision_decision",
        ),
        CheckConstraint("version >= 1", name="ck_revision_version"),
        Index("ix_revisions_workspace_created", "workspace_id", "created_at"),
    )


class DecisionSource(Base):
    __tablename__ = "decision_sources"
    workspace_id = Column(String, primary_key=True)
    decision_id = Column(String, primary_key=True)
    revision = Column(Integer, primary_key=True)
    kind = Column(String(16), primary_key=True)
    source_id = Column(String, primary_key=True)
    snapshot = Column(JSON, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "decision_id", "revision"],
            [
                "decision_revisions.workspace_id",
                "decision_revisions.decision_id",
                "decision_revisions.version",
            ],
            name="fk_source_revision",
        ),
        CheckConstraint("kind IN ('message','task','activity','decision')", name="ck_source_kind"),
    )


class WorkspaceVisit(Base):
    __tablename__ = "workspace_visits"
    workspace_id = Column(String, ForeignKey("workspaces.id"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    through = Column(DateTime, nullable=False)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    initiator_id = Column(String, ForeignKey("users.id"), nullable=False)
    agent_type = Column(String(64), nullable=False)
    objective = Column(String(1000), nullable=False)
    task_id = Column(String)
    parent_id = Column(String)
    idempotency_key = Column(String(100))
    request_hash = Column(String(64), nullable=False)
    input_refs = Column(JSON, nullable=False)
    publish = Column(Boolean, nullable=False, server_default=false())
    state = Column(String(32), nullable=False)
    attempt = Column(Integer, nullable=False, default=1)
    retry_of_id = Column(String)
    lease_token = Column(String)
    lease_until = Column(DateTime)
    context = Column(JSON)
    outcome = Column(JSON)
    error_code = Column(String(64))
    created_at = Column(DateTime, default=utc_now, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_run_workspace_id"),
        UniqueConstraint(
            "workspace_id", "initiator_id", "idempotency_key", name="uq_run_idempotency"
        ),
        UniqueConstraint("retry_of_id", name="uq_run_retry_once"),
        ForeignKeyConstraint(
            ["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_run_task"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "parent_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_run_parent",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "retry_of_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_run_retry",
        ),
        CheckConstraint(
            "state IN ('queued','running','waiting_for_approval','completed','failed','cancelled')",
            name="ck_run_state",
        ),
        CheckConstraint("attempt BETWEEN 1 AND 3", name="ck_run_attempt"),
        Index("ix_runs_queue", "state", "created_at"),
        Index("ix_runs_workspace_created", "workspace_id", "created_at", "id"),
    )


class RunEvent(Base):
    __tablename__ = "run_events"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False)
    run_id = Column(String, nullable=False)
    event = Column(String(64), nullable=False)
    detail = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_event_run",
        ),
        Index("ix_run_events", "run_id", "created_at", "id"),
    )


class Approval(Base):
    __tablename__ = "approvals"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False)
    run_id = Column(String, nullable=False, unique=True)
    action = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    state = Column(String(16), nullable=False)
    approver_id = Column(String, ForeignKey("users.id"))
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    responded_at = Column(DateTime)
    executed_at = Column(DateTime)
    message_id = Column(String, ForeignKey("messages.id"), unique=True)
    error_code = Column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_approval_run",
        ),
        CheckConstraint(
            "state IN ('pending','approved','rejected','expired','executed','failed','cancelled')",
            name="ck_approval_state",
        ),
        CheckConstraint("action='publish_report'", name="ck_approval_action"),
        Index("ix_approvals_workspace_state", "workspace_id", "state", "created_at"),
    )


class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    creator_id = Column(String, ForeignKey("users.id"), nullable=False)
    filename = Column(String(200), nullable=False)
    title = Column(String(200), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    archived = Column(Boolean, nullable=False, server_default=false())
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_document_workspace"),
        CheckConstraint("version >= 1", name="ck_document_version"),
        Index("ix_documents_workspace", "workspace_id", "created_at", "id"),
    )


class DocumentRevision(Base):
    __tablename__ = "document_revisions"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False)
    document_id = Column(String, nullable=False)
    creator_id = Column(String, ForeignKey("users.id"), nullable=False)
    filename = Column(String(200), nullable=False)
    title = Column(String(200), nullable=False)
    version = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False)
    state = Column(String(16), nullable=False)
    raw_content = Column(LargeBinary)
    error_code = Column(String(64))
    lease_token = Column(String)
    lease_until = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    completed_at = Column(DateTime)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_document_revision_workspace"),
        UniqueConstraint("document_id", "version", name="uq_document_revision_number"),
        ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            name="fk_document_revision",
        ),
        CheckConstraint("version >= 1", name="ck_document_revision_version"),
        CheckConstraint(
            "state IN ('queued','processing','ready','failed','cancelled')",
            name="ck_document_revision_state",
        ),
        Index("ix_document_queue", "state", "created_at"),
    )


class DocumentPassage(Base):
    __tablename__ = "document_passages"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False)
    revision_id = Column(String, nullable=False)
    ordinal = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "revision_id"],
            ["document_revisions.workspace_id", "document_revisions.id"],
            name="fk_document_passage_revision",
        ),
        UniqueConstraint("revision_id", "ordinal", name="uq_document_passage_ordinal"),
        Index("ix_document_passages_workspace", "workspace_id", "revision_id"),
    )


class RepositoryConnection(Base):
    __tablename__ = "repository_connections"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    creator_id = Column(String, ForeignKey("users.id"), nullable=False)
    repository = Column(String(200), nullable=False)
    active = Column(Boolean, nullable=False, server_default=false())
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_connection_workspace"),
        Index("ix_connections_workspace", "workspace_id", "created_at"),
    )


class RepositorySync(Base):
    __tablename__ = "repository_syncs"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False)
    connection_id = Column(String, nullable=False)
    initiator_id = Column(String, ForeignKey("users.id"), nullable=False)
    connection_version = Column(Integer, nullable=False)
    state = Column(String(16), nullable=False)
    attempt = Column(Integer, nullable=False, default=0)
    lease_token = Column(String)
    lease_until = Column(DateTime)
    next_attempt_at = Column(DateTime, nullable=False, default=utc_now)
    error_code = Column(String(64))
    record_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    completed_at = Column(DateTime)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["repository_connections.workspace_id", "repository_connections.id"],
            name="fk_sync_connection",
        ),
        CheckConstraint(
            "state IN ('queued','running','completed','failed','cancelled')", name="ck_sync_state"
        ),
        CheckConstraint("attempt BETWEEN 0 AND 3", name="ck_sync_attempt"),
        Index("ix_sync_queue", "state", "next_attempt_at"),
    )


class ImportedRecord(Base):
    __tablename__ = "imported_records"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False)
    connection_id = Column(String, nullable=False)
    provider_id = Column(String(100), nullable=False)
    available = Column(Boolean, nullable=False, server_default=false())
    record_type = Column(String(32), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    original_url = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["repository_connections.workspace_id", "repository_connections.id"],
            name="fk_import_connection",
        ),
        UniqueConstraint("connection_id", "provider_id", name="uq_import_provider"),
        Index("ix_import_workspace", "workspace_id", "updated_at", "id"),
    )


class KnowledgeAnswer(Base):
    __tablename__ = "knowledge_answers"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    creator_id = Column(String, ForeignKey("users.id"), nullable=False)
    question = Column(String(200), nullable=False)
    mode = Column(String(16), nullable=False)
    provider_model = Column(String(200))
    idempotency_key = Column(String(100), nullable=False)
    state = Column(String(16), nullable=False)
    claims = Column(JSON, nullable=False)
    evidence = Column(JSON, nullable=False)
    error_code = Column(String(64))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    completed_at = Column(DateTime)
    __table_args__ = (
        UniqueConstraint("workspace_id", "creator_id", "idempotency_key", name="uq_answer_request"),
        CheckConstraint(
            "state IN ('processing','completed','abstained','failed')", name="ck_answer_state"
        ),
        CheckConstraint("mode IN ('extractive','model')", name="ck_answer_mode"),
        Index("ix_answers_workspace", "workspace_id", "created_at", "id"),
    )


class ActionProposal(Base):
    __tablename__ = "action_proposals"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False)
    run_id = Column(String, nullable=False, unique=True)
    action = Column(String(32), nullable=False)
    payload = Column(JSON, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    state = Column(String(16), nullable=False)
    approver_id = Column(String, ForeignKey("users.id"))
    receipt = Column(JSON)
    error_code = Column(String(64))
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
    responded_at = Column(DateTime)
    executed_at = Column(DateTime)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_action_run",
        ),
        CheckConstraint("action='create_task_plan'", name="ck_action_kind"),
        CheckConstraint(
            "state IN ('pending','approved','rejected','expired','executed','failed','cancelled')",
            name="ck_action_state",
        ),
        Index("ix_action_workspace", "workspace_id", "state", "created_at"),
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id = Column(String, primary_key=True)
    state = Column(String(16), nullable=False)
    last_seen_at = Column(DateTime, nullable=False, default=utc_now)
    __table_args__ = (CheckConstraint("state IN ('running','stopped')", name="ck_worker_state"),)
