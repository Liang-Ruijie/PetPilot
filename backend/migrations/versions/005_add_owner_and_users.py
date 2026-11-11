"""add users table + owner_id to all business tables

Revision ID: 005
Revises: 004
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

_TABLES = ["pets", "messages", "facts", "held_segments", "corrections", "reminders", "care_summaries", "photos", "weekly_reviews"]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("label", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=False),
    )
    for t in _TABLES:
        op.add_column(t, sa.Column("owner_id", sa.String(64), nullable=True))
        op.create_index(f"ix_{t}_owner_id", t, ["owner_id"])


def downgrade() -> None:
    for t in _TABLES:
        op.drop_index(f"ix_{t}_owner_id", table_name=t)
        op.drop_column(t, "owner_id")
    op.drop_table("users")
