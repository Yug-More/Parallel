"""Privately backfill each legacy user's records, never a global shared room."""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0002_workspaces"
down_revision = "0001_legacy"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Refuse ambiguous ownership rather than delete or expose orphan records.
    for table in ("messages", "activities", "user_credentials"):
        if bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} t LEFT JOIN users u ON t.user_id=u.id WHERE u.id IS NULL"
            )
        ).scalar():
            raise RuntimeError(f"Orphan ownership in {table}; migration requires owner review")
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("owner_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_workspaces_owner_id", "workspaces", ["owner_id"])
    op.create_table(
        "workspace_memberships",
        sa.Column("workspace_id", sa.String, sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("role IN ('owner', 'member')", name="ck_membership_role"),
    )
    op.create_index("ix_workspace_memberships_user_id", "workspace_memberships", ["user_id"])
    for table in ("messages", "activities"):
        op.add_column(table, sa.Column("workspace_id", sa.String, nullable=True))
    migration_time = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    for table in ("users", "user_credentials", "messages", "activities"):
        bind.execute(
            sa.text(f"UPDATE {table} SET created_at=:now WHERE created_at IS NULL"),
            {"now": migration_time},
        )
    for user in bind.execute(sa.text("SELECT id, name FROM users")).mappings():
        workspace_id = str(uuid5(NAMESPACE_URL, f"parallel:legacy-private:{user['id']}"))
        params = {
            "id": workspace_id,
            "name": f"{user['name']}'s private workspace"[:120],
            "owner": user["id"],
            "now": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" "),
        }
        bind.execute(
            sa.text(
                "INSERT INTO workspaces (id,name,owner_id,created_at) VALUES (:id,:name,:owner,:now)"
            ),
            params,
        )
        bind.execute(
            sa.text(
                "INSERT INTO workspace_memberships (workspace_id,user_id,role,created_at) VALUES (:id,:owner,'owner',:now)"
            ),
            params,
        )
        for table in ("messages", "activities"):
            bind.execute(
                sa.text(f"UPDATE {table} SET workspace_id=:id WHERE user_id=:owner"), params
            )
    for table in ("messages", "activities"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column("workspace_id", existing_type=sa.String, nullable=False)
            batch.create_foreign_key(
                f"fk_{table}_workspace", "workspaces", ["workspace_id"], ["id"]
            )
        fields = (
            ["workspace_id", "created_at", "id"]
            if table == "messages"
            else ["workspace_id", "created_at"]
        )
        op.create_index(f"ix_{table}_workspace_created", table, fields)


def downgrade():
    raise RuntimeError("Removing workspace ownership would weaken isolation; downgrade is disabled")
