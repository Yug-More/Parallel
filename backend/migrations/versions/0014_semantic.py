"""Versioned trained retrieval metadata; existing character indexes unchanged."""

import sqlalchemy as sa
from alembic import op

revision = "0014_semantic"
down_revision = "0013_shared_limits"
branch_labels = depends_on = None


def upgrade():
    for column in [
        sa.Column("dimensions", sa.Integer()),
        sa.Column("options", sa.JSON()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("input_characters", sa.Integer()),
        sa.Column("usage_tokens", sa.Integer()),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
    ]:
        op.add_column("retrieval_indexes", column)
    op.add_column("agent_runs", sa.Column("knowledge_refs", sa.JSON()))


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a reviewed backup")
