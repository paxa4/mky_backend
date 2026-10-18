"""add persistent audit log and portal settings

Revision ID: c7d8e9f0a1b2
Revises: a3f9c1d8e2b7
Create Date: 2026-10-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "a3f9c1d8e2b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portal_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("portal_name", sa.String(length=200), nullable=False, server_default="МКУ ИМЦРО"),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=100), nullable=True),
        sa.Column("contact_address", sa.String(length=500), nullable=True),
        sa.Column("footer_text", sa.String(length=500), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_name", sa.String(length=255), nullable=True),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("audit_log_created_idx", "audit_log", ["created_at"])
    op.create_index("audit_log_user_idx", "audit_log", ["user_id"])


def downgrade() -> None:
    op.drop_index("audit_log_user_idx", table_name="audit_log")
    op.drop_index("audit_log_created_idx", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("portal_settings")
