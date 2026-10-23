"""Bounded, versioned optional retrieval index jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0011_retrieval_index"
down_revision = "0010_pdf_pages"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "retrieval_indexes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("creator_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("lease_token", sa.String()),
        sa.Column("lease_until", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.CheckConstraint(
            "state IN ('queued','running','ready','failed','cancelled')",
            name="ck_retrieval_index_state",
        ),
    )
    op.create_index(
        "ix_retrieval_index_queue", "retrieval_indexes", ["workspace_id", "state", "created_at"]
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a reviewed backup")
