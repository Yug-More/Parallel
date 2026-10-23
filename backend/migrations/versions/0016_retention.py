"""Explicit retention receipts and workspace closure; no data deletion on upgrade."""

import sqlalchemy as sa
from alembic import op

revision = "0016_retention"
down_revision = "0015_recovery"
branch_labels = depends_on = None


def upgrade():
    op.add_column("workspaces", sa.Column("closed_at", sa.DateTime()))
    op.create_table(
        "retention_receipts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("actor_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("plan_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a reviewed backup")
