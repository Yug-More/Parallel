"""Durable read-only repository connections and imported provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0006_repositories"
down_revision = "0005_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "repository_connections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("creator_id", sa.String(), nullable=False),
        sa.Column("repository", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_connection_workspace"),
    )
    op.create_index(
        "ix_connections_workspace",
        "repository_connections",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "repository_syncs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("connection_id", sa.String(), nullable=False),
        sa.Column("initiator_id", sa.String(), nullable=False),
        sa.Column("connection_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "state IN ('queued','running','completed','failed','cancelled')", name="ck_sync_state"
        ),
        sa.CheckConstraint("attempt BETWEEN 0 AND 3", name="ck_sync_attempt"),
        sa.ForeignKeyConstraint(
            ["initiator_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["repository_connections.workspace_id", "repository_connections.id"],
            name="fk_sync_connection",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_queue", "repository_syncs", ["state", "next_attempt_at"], unique=False)
    op.create_table(
        "imported_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("connection_id", sa.String(), nullable=False),
        sa.Column("provider_id", sa.String(length=100), nullable=False),
        sa.Column("available", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("record_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("original_url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["repository_connections.workspace_id", "repository_connections.id"],
            name="fk_import_connection",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", "provider_id", name="uq_import_provider"),
    )
    op.create_index(
        "ix_import_workspace",
        "imported_records",
        ["workspace_id", "updated_at", "id"],
        unique=False,
    )


def downgrade():
    raise RuntimeError("Destructive connector downgrade disabled; restore a reviewed backup")
