"""add editable public contact information

Revision ID: e7c4a2b9d1f0
Revises: d9e4f2a7c1b6
Create Date: 2026-11-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7c4a2b9d1f0"
down_revision: Union[str, Sequence[str], None] = "d9e4f2a7c1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_contact_info",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="Контактная информация"),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("contacts", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path", name="site_contact_info_path_unique"),
    )
    op.create_index(op.f("ix_site_contact_info_id"), "site_contact_info", ["id"], unique=False)
    op.create_index(op.f("ix_site_contact_info_path"), "site_contact_info", ["path"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_site_contact_info_path"), table_name="site_contact_info")
    op.drop_index(op.f("ix_site_contact_info_id"), table_name="site_contact_info")
    op.drop_table("site_contact_info")
