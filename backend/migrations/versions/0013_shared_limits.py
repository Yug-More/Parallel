"""Shared fixed-window abuse counters, containing only HMAC keys."""

import sqlalchemy as sa
from alembic import op

revision = "0013_shared_limits"
down_revision = "0012_private_github"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "abuse_counters",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window", sa.BigInteger(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a reviewed backup")
