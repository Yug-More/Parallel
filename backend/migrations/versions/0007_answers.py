"""Persist bounded answers with revalidated evidence references."""

import sqlalchemy as sa
from alembic import op

revision = "0007_answers"
down_revision = "0006_repositories"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_answers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("creator_id", sa.String(), nullable=False),
        sa.Column("question", sa.String(length=200), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("provider_model", sa.String(200)),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("mode IN ('extractive','model')", name="ck_answer_mode"),
        sa.CheckConstraint(
            "state IN ('processing','completed','abstained','failed')", name="ck_answer_state"
        ),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "creator_id", "idempotency_key", name="uq_answer_request"
        ),
    )
    op.create_index(
        "ix_answers_workspace",
        "knowledge_answers",
        ["workspace_id", "created_at", "id"],
        unique=False,
    )


def downgrade():
    raise RuntimeError("Destructive answer downgrade disabled; restore a reviewed backup")
