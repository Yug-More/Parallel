"""Add invitations, tasks, revocable sessions and workspace mutation serialization."""

import sqlalchemy as sa
from alembic import op

revision = "0003_collaboration"
down_revision = "0002_workspaces"
branch_labels = None
depends_on = None


def upgrade():
    inconsistent = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT COUNT(*) FROM (SELECT w.id FROM workspaces w "
                "LEFT JOIN workspace_memberships m ON m.workspace_id=w.id AND m.role='owner' "
                "GROUP BY w.id,w.owner_id HAVING COUNT(m.user_id)<>1 OR MAX(m.user_id)<>w.owner_id) invalid"
            )
        )
        .scalar()
    )
    if inconsistent:
        raise RuntimeError(
            "Inconsistent workspace ownership; preserve the backup and review before migration"
        )
    op.add_column(
        "workspaces", sa.Column("revision", sa.Integer, nullable=False, server_default="0")
    )
    op.create_index(
        "uq_workspace_one_owner",
        "workspace_memberships",
        ["workspace_id"],
        unique=True,
        sqlite_where=sa.text("role='owner'"),
        postgresql_where=sa.text("role='owner'"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "workspace_invitations",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("workspace_id", sa.String, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("recipient_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("inviter_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("responded_at", sa.DateTime),
        sa.CheckConstraint(
            "status IN ('pending','accepted','declined','revoked','expired')",
            name="ck_invitation_status",
        ),
    )
    op.create_index(
        "ix_workspace_invitations_workspace_id", "workspace_invitations", ["workspace_id"]
    )
    op.create_index(
        "ix_workspace_invitations_recipient_id", "workspace_invitations", ["recipient_id"]
    )
    op.create_index(
        "uq_invitation_pending",
        "workspace_invitations",
        ["workspace_id", "recipient_id"],
        unique=True,
        sqlite_where=sa.text("status='pending'"),
        postgresql_where=sa.text("status='pending'"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("workspace_id", sa.String, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("creator_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assignee_id", sa.String),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("due_date", sa.Date),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_tasks_workspace_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "assignee_id"],
            ["workspace_memberships.workspace_id", "workspace_memberships.user_id"],
            name="fk_tasks_assignee_membership",
        ),
        sa.CheckConstraint(
            "status IN ('todo','in_progress','blocked','done')", name="ck_task_status"
        ),
        sa.CheckConstraint("priority IN ('low','medium','high','urgent')", name="ck_task_priority"),
        sa.CheckConstraint("version >= 1", name="ck_task_version"),
    )
    op.create_index("ix_tasks_workspace_created", "tasks", ["workspace_id", "created_at", "id"])
    op.create_table(
        "task_dependencies",
        sa.Column("workspace_id", sa.String, primary_key=True),
        sa.Column("task_id", sa.String, primary_key=True),
        sa.Column("depends_on_id", sa.String, primary_key=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["tasks.workspace_id", "tasks.id"],
            name="fk_dependency_task",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "depends_on_id"],
            ["tasks.workspace_id", "tasks.id"],
            name="fk_dependency_prerequisite",
        ),
        sa.CheckConstraint("task_id <> depends_on_id", name="ck_dependency_not_self"),
    )
    op.create_index(
        "ix_dependency_prerequisite", "task_dependencies", ["workspace_id", "depends_on_id"]
    )


def downgrade():
    raise RuntimeError("Destructive collaboration downgrade is disabled; restore a reviewed backup")
