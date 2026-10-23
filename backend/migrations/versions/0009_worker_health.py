"""Persist worker liveness without exposing process or host details."""

import sqlalchemy as sa
from alembic import op

revision = "0009_worker_health"
down_revision = "0008_actions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("state IN ('running','stopped')", name="ck_worker_state"),
    )


def downgrade():
    raise RuntimeError("Destructive worker health downgrade disabled; restore a reviewed backup")
