"""add corrections, reminders, care_summaries, photos

Revision ID: 002
Revises: 001
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corrections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fact_id", sa.Integer(), sa.ForeignKey("facts.id"), nullable=False),
        sa.Column("old_value", sa.Float(), nullable=True),
        sa.Column("new_value", sa.Float(), nullable=True),
        sa.Column("old_topic", sa.String(50), nullable=True),
        sa.Column("new_topic", sa.String(50), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("source_message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id"), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "care_summaries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("fact_ids", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "photos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id"), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("photos")
    op.drop_table("care_summaries")
    op.drop_table("reminders")
    op.drop_table("corrections")
