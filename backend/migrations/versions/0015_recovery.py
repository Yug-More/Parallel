"""Opt-in account recovery; no existing account is implicitly verified."""

import sqlalchemy as sa
from alembic import op

revision = "0015_recovery"
down_revision = "0014_semantic"
branch_labels = depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime()))
    op.create_table(
        "recovery_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id")),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("used_at", sa.DateTime()),
        sa.CheckConstraint("purpose IN ('reset','verify')", name="ck_recovery_purpose"),
        sa.CheckConstraint(
            "state IN ('queued','running','delivered','failed','consumed','superseded')",
            name="ck_recovery_state",
        ),
    )
    op.create_index("ix_recovery_user", "recovery_requests", ["user_id", "purpose", "created_at"])


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a reviewed backup")
