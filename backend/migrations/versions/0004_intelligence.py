"""Persist decision provenance, visits, agent runs and approvals without changing existing records."""

import sqlalchemy as sa
from alembic import op

revision = "0004_intelligence"
down_revision = "0003_collaboration"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("alternatives", sa.Text(), nullable=False),
        sa.Column("tradeoffs", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("creator_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("superseded_by_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed','accepted','superseded','rejected')", name="ck_decision_status"
        ),
        sa.CheckConstraint(
            "superseded_by_id IS NULL OR (superseded_by_id <> id AND status='superseded')",
            name="ck_decision_successor",
        ),
        sa.CheckConstraint("version >= 1", name="ck_decision_version"),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "superseded_by_id"],
            ["decisions.workspace_id", "decisions.id"],
            name="fk_decision_successor",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_decision_workspace_id"),
    )
    with op.batch_alter_table("decisions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_decisions_workspace_updated", ["workspace_id", "updated_at", "id"], unique=False
        )

    op.create_table(
        "workspace_visits",
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("through", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
    )
    op.create_table(
        "decision_revisions",
        sa.Column("decision_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_revision_version"),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "decision_id"],
            ["decisions.workspace_id", "decisions.id"],
            name="fk_revision_decision",
        ),
        sa.PrimaryKeyConstraint("decision_id", "version"),
        sa.UniqueConstraint("workspace_id", "decision_id", "version", name="uq_revision_workspace"),
    )
    with op.batch_alter_table("decision_revisions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_revisions_workspace_created", ["workspace_id", "created_at"], unique=False
        )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("initiator_id", sa.String(), nullable=False),
        sa.Column("agent_type", sa.String(length=64), nullable=False),
        sa.Column("objective", sa.String(length=1000), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("parent_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("input_refs", sa.JSON(), nullable=False),
        sa.Column("publish", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("retry_of_id", sa.String(), nullable=True),
        sa.Column("lease_token", sa.String(), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("outcome", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "state IN ('queued','running','waiting_for_approval','completed','failed','cancelled')",
            name="ck_run_state",
        ),
        sa.CheckConstraint("attempt BETWEEN 1 AND 3", name="ck_run_attempt"),
        sa.ForeignKeyConstraint(
            ["initiator_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "parent_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_run_parent",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "retry_of_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_run_retry",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_run_task"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_run_workspace_id"),
        sa.UniqueConstraint(
            "workspace_id", "initiator_id", "idempotency_key", name="uq_run_idempotency"
        ),
        sa.UniqueConstraint("retry_of_id", name="uq_run_retry_once"),
    )
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.create_index("ix_runs_queue", ["state", "created_at"], unique=False)
        batch_op.create_index(
            "ix_runs_workspace_created", ["workspace_id", "created_at", "id"], unique=False
        )

    op.create_table(
        "decision_sources",
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("decision_id", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('message','task','activity','decision')", name="ck_source_kind"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "decision_id", "revision"],
            [
                "decision_revisions.workspace_id",
                "decision_revisions.decision_id",
                "decision_revisions.version",
            ],
            name="fk_source_revision",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "decision_id", "revision", "kind", "source_id"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("approver_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint("action='publish_report'", name="ck_approval_action"),
        sa.CheckConstraint(
            "state IN ('pending','approved','rejected','expired','executed','failed','cancelled')",
            name="ck_approval_state",
        ),
        sa.ForeignKeyConstraint(
            ["approver_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_approval_run",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
        sa.UniqueConstraint("run_id"),
    )
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.create_index(
            "ix_approvals_workspace_state", ["workspace_id", "state", "created_at"], unique=False
        )

    op.create_table(
        "run_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_event_run",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("run_events", schema=None) as batch_op:
        batch_op.create_index("ix_run_events", ["run_id", "created_at", "id"], unique=False)


def downgrade():
    raise RuntimeError("Destructive intelligence downgrade is disabled; restore a reviewed backup")
