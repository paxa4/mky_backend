"""store the complete practice application

Revision ID: d9e4f2a7c1b6
Revises: c8d1e4a7b2f6
Create Date: 2026-11-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9e4f2a7c1b6"
down_revision: Union[str, Sequence[str], None] = "c8d1e4a7b2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("practice", sa.Column("practice_type", sa.String(length=40), nullable=True))
    op.add_column("practice", sa.Column("implementation_level", sa.String(length=40), nullable=True))
    op.add_column(
        "practice",
        sa.Column("application_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("practice", "application_data")
    op.drop_column("practice", "implementation_level")
    op.drop_column("practice", "practice_type")
