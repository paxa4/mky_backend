"""add educational practices catalog

Revision ID: f1a2b3c4d5e6
Revises: c7d8e9f0a1b2
Create Date: 2026-10-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "practice",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("summary", sa.String(length=1200), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=False, server_default="Начальный"),
        sa.Column("organization", sa.String(length=300), nullable=False),
        sa.Column("municipality", sa.String(length=200), nullable=True),
        sa.Column("author_name", sa.String(length=200), nullable=False),
        sa.Column("author_email", sa.String(length=255), nullable=True),
        sa.Column("target_audience", sa.String(length=500), nullable=True),
        sa.Column("implementation_period", sa.String(length=200), nullable=True),
        sa.Column("results", sa.Text(), nullable=True),
        sa.Column("materials", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("cover_image_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'draft', 'published', 'archive')",
            name="practice_status_chk",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_practice_id"), "practice", ["id"], unique=False)
    op.create_index(op.f("ix_practice_slug"), "practice", ["slug"], unique=True)
    op.create_index("practice_status_idx", "practice", ["status"], unique=False)
    op.create_index("practice_topic_idx", "practice", ["topic"], unique=False)
    op.create_index("practice_level_idx", "practice", ["level"], unique=False)


def downgrade() -> None:
    op.drop_index("practice_level_idx", table_name="practice")
    op.drop_index("practice_topic_idx", table_name="practice")
    op.drop_index("practice_status_idx", table_name="practice")
    op.drop_index(op.f("ix_practice_slug"), table_name="practice")
    op.drop_index(op.f("ix_practice_id"), table_name="practice")
    op.drop_table("practice")
