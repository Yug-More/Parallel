"""Adopt the four legacy tables without replacing existing records."""

import sqlalchemy as sa
from alembic import op

revision = "0001_legacy"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    tables = {
        "users": [
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("email", sa.String, nullable=False),
            sa.Column("name", sa.String, nullable=False),
            sa.Column("role", sa.String),
            sa.Column("created_at", sa.DateTime),
            sa.Column("last_seen_at", sa.DateTime),
        ],
        "user_credentials": [
            sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("password_hash", sa.String, nullable=False),
            sa.Column("created_at", sa.DateTime),
        ],
        "messages": [
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("sender_id", sa.String, nullable=False),
            sa.Column("sender_name", sa.String, nullable=False),
            sa.Column("role", sa.String, nullable=False),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime),
        ],
        "activities": [
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("user_name", sa.String, nullable=False),
            sa.Column("summary", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime),
        ],
    }
    for name, columns in tables.items():
        if name in existing:
            actual = {c["name"] for c in sa.inspect(bind).get_columns(name)}
            if not {c.name for c in columns}.issubset(actual):
                raise RuntimeError(
                    f"Unsupported legacy schema in {name}; back up and review before migrating"
                )
        else:
            op.create_table(name, *columns)

    indexes = {
        "users": ["id", "email"],
        "messages": ["id", "user_id", "created_at"],
        "activities": ["id", "user_id", "created_at"],
    }
    for table, columns in indexes.items():
        existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
        for column in columns:
            name = f"ix_{table}_{column}"
            if name not in existing_indexes:
                op.create_index(
                    name, table, [column], unique=table == "users" and column == "email"
                )


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a reviewed backup instead")
