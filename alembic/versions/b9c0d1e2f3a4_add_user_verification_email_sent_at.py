"""add users.verification_email_sent_at (cooldown for verification emails)

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-11-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    return column_name in {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    if _table_exists("users") and not _column_exists("users", "verification_email_sent_at"):
        # Время последней отправки письма подтверждения. NULL — письмо ещё не отправлялось
        op.add_column(
            "users",
            sa.Column("verification_email_sent_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if _table_exists("users") and _column_exists("users", "verification_email_sent_at"):
        op.drop_column("users", "verification_email_sent_at")
