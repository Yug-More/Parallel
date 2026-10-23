"""Preserve page provenance on new PDF passages; existing passages stay unchanged."""

import sqlalchemy as sa
from alembic import op

revision = "0010_pdf_pages"
down_revision = "0009_worker_health"
branch_labels = depends_on = None


def upgrade():
    op.add_column("document_passages", sa.Column("page_number", sa.Integer(), nullable=True))


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a reviewed backup")
