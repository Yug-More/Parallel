"""Encrypted expiring GitHub App grants and explicit workspace mapping."""

import sqlalchemy as sa
from alembic import op

revision = "0012_private_github"
down_revision = "0011_retrieval_index"
branch_labels = depends_on = None


def upgrade():
    for column in [
        sa.Column(
            "auth_mode", sa.String(32), server_default="public_unauthenticated", nullable=False
        ),
        sa.Column("installation_id", sa.BigInteger()),
        sa.Column("repository_id", sa.BigInteger()),
        sa.Column("credential", sa.Text()),
        sa.Column("credential_expires_at", sa.DateTime()),
        sa.Column("access_verified_until", sa.DateTime()),
    ]:
        op.add_column("repository_connections", column)
    op.create_table(
        "github_authorizations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("creator_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("repository", sa.String(200), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("device_secret", sa.Text()),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("next_poll_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending','completed','failed','expired')", name="ck_github_auth_state"
        ),
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a reviewed backup")
