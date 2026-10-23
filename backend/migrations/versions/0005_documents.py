"""Add bounded local document ingestion without changing existing records."""

import sqlalchemy as sa
from alembic import op

revision = "0005_documents"
down_revision = "0004_intelligence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("creator_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_document_workspace"),
        sa.CheckConstraint("version >= 1", name="ck_document_version"),
    )
    op.create_index("ix_documents_workspace", "documents", ["workspace_id", "created_at", "id"])
    op.create_table(
        "document_revisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("creator_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("raw_content", sa.LargeBinary()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("lease_token", sa.String()),
        sa.Column("lease_until", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.UniqueConstraint("workspace_id", "id", name="uq_document_revision_workspace"),
        sa.UniqueConstraint("document_id", "version", name="uq_document_revision_number"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            name="fk_document_revision",
        ),
        sa.CheckConstraint("version >= 1", name="ck_document_revision_version"),
        sa.CheckConstraint(
            "state IN ('queued','processing','ready','failed','cancelled')",
            name="ck_document_revision_state",
        ),
    )
    op.create_index("ix_document_queue", "document_revisions", ["state", "created_at"])
    op.create_table(
        "document_passages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("revision_id", sa.String(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "revision_id"],
            ["document_revisions.workspace_id", "document_revisions.id"],
            name="fk_document_passage_revision",
        ),
        sa.UniqueConstraint("revision_id", "ordinal", name="uq_document_passage_ordinal"),
    )
    op.create_index(
        "ix_document_passages_workspace", "document_passages", ["workspace_id", "revision_id"]
    )


def downgrade():
    raise RuntimeError("Destructive document downgrade disabled; restore a reviewed backup")
