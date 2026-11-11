"""init schema

Revision ID: 001
Revises:
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "pets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "facts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id"), nullable=False),
        sa.Column("topic", sa.String(50), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("quantity_scope", sa.String(20), nullable=True),
        sa.Column("historical_current", sa.String(20), nullable=True),
        sa.Column("occurred_at", sa.Date(), nullable=True),
        sa.Column("polarity", sa.String(20), nullable=True),
        sa.Column("change_kind", sa.String(20), nullable=False),
        sa.Column("source_message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "held_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(50), nullable=True),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("resolved_pet_id", sa.Integer(), sa.ForeignKey("pets.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("held_segments")
    op.drop_table("facts")
    op.drop_table("messages")
    op.drop_table("pets")
    op.drop_table("sessions")
