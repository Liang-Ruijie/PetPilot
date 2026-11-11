"""add held_segment fields + stale flags

Revision ID: 004
Revises: 003
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("facts", "source_message_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("held_segments", sa.Column("value", sa.Float(), nullable=True))
    op.add_column("held_segments", sa.Column("unit", sa.String(20), nullable=True))
    op.add_column("held_segments", sa.Column("quantity_scope", sa.String(20), nullable=True))
    op.add_column("held_segments", sa.Column("historical_current", sa.String(20), nullable=True))
    op.add_column("held_segments", sa.Column("occurred_at", sa.Date(), nullable=True))
    op.add_column("held_segments", sa.Column("polarity", sa.String(20), nullable=True))
    op.add_column("care_summaries", sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("weekly_reviews", sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("weekly_reviews", "stale")
    op.drop_column("care_summaries", "stale")
    op.drop_column("held_segments", "polarity")
    op.drop_column("held_segments", "occurred_at")
    op.drop_column("held_segments", "historical_current")
    op.drop_column("held_segments", "quantity_scope")
    op.drop_column("held_segments", "unit")
    op.drop_column("held_segments", "value")
    op.alter_column("facts", "source_message_id", existing_type=sa.Integer(), nullable=False)
