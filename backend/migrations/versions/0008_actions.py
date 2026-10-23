"""Native action receipts and conservative knowledge revocation epochs."""

import sqlalchemy as sa
from alembic import op

revision = "0008_actions"
down_revision = "0007_answers"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspaces", sa.Column("knowledge_epoch", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("messages", sa.Column("knowledge_epoch", sa.Integer()))
    op.create_table(
        "action_proposals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("approver_id", sa.String(), nullable=True),
        sa.Column("receipt", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("action='create_task_plan'", name="ck_action_kind"),
        sa.CheckConstraint(
            "state IN ('pending','approved','rejected','expired','executed','failed','cancelled')",
            name="ck_action_state",
        ),
        sa.ForeignKeyConstraint(
            ["approver_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_action_run",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(
        "ix_action_workspace",
        "action_proposals",
        ["workspace_id", "state", "created_at"],
        unique=False,
    )


def downgrade():
    raise RuntimeError("Destructive actions downgrade disabled; restore a reviewed backup")
