"""add user email_verified flag

Revision ID: a8b9c0d1e2f3
Revises: f1a2b3c4d5e6
Create Date: 2026-11-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
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
    if not _table_exists("users"):
        return

    if not _column_exists("users", "email_verified"):
        # Новая колонка: по умолчанию почта НЕ подтверждена
        op.add_column(
            "users",
            sa.Column(
                "email_verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        # Все пользователи, созданные до этой миграции, считаются подтверждёнными,
        # чтобы никто из существующих не потерял доступ к сайту
        op.execute("UPDATE users SET email_verified = TRUE")


def downgrade() -> None:
    if _table_exists("users") and _column_exists("users", "email_verified"):
        op.drop_column("users", "email_verified")
