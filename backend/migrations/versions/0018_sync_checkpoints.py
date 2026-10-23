"""Atomic successful reconciliation checkpoints; no remote delta claims."""

import sqlalchemy as sa
from alembic import op

revision = "0018_sync_checkpoints"
down_revision = "0017_answer_retrieval"
branch_labels = depends_on = None


def upgrade():
    op.add_column("repository_connections", sa.Column("sync_checkpoint", sa.JSON()))
    op.add_column("repository_syncs", sa.Column("checkpoint", sa.JSON()))


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a reviewed backup")
