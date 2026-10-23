"""Bind saved answer requests to their explicit retrieval selection."""

import sqlalchemy as sa
from alembic import op

revision = "0017_answer_retrieval"
down_revision = "0016_retention"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "knowledge_answers",
        sa.Column("retrieval_mode", sa.String(16), nullable=False, server_default="lexical"),
    )
    op.add_column("knowledge_answers", sa.Column("evidence_plan", sa.JSON()))


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a reviewed backup")
