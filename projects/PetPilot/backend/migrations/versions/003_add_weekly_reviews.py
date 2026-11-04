"""add weekly_reviews

Revision ID: 003
Revises: 002
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weekly_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id"), nullable=True),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("fact_ids", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("weekly_reviews")
