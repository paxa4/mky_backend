"""add article content and status_id columns

Revision ID: a3f9c1d8e2b7
Revises: e0f1a2b3c4d5
Create Date: 2026-09-28 00:00:00.000000

Эти два поля объявлены в модели Article (models/__init__.py), но ни одна
из прежних миграций их не создавала. Из-за этого на любой свежей базе,
поднятой через `alembic upgrade head`, запросы к /api/news/, /api/events/,
/api/admin/news/ падали с ошибкой:
    psycopg2.errors.UndefinedColumn: column article.content does not exist
    psycopg2.errors.UndefinedColumn: column article.status_id does not exist

Заодно таблица article_status (модель ArticleStatus), на которую ссылается
article.status_id, тоже никогда не создавалась ни одной миграцией — она
появлялась только благодаря Base.metadata.create_all() при старте
приложения. Эта миграция создаёт её явно, чтобы alembic upgrade head
отрабатывал самостоятельно, без зависимости от предварительного запуска
самого приложения.

Эта миграция закрывает расхождение между моделью и реальной схемой БД.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3f9c1d8e2b7"
down_revision: Union[str, Sequence[str], None] = "e0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "article_status"):
        op.create_table(
            "article_status",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("name", sa.String(length=50), nullable=False, unique=True),
        )
        inspector = sa.inspect(bind)

    if not _has_column(inspector, "article", "content"):
        op.add_column("article", sa.Column("content", sa.Text(), nullable=True))

    if not _has_column(inspector, "article", "status_id"):
        op.add_column(
            "article",
            sa.Column(
                "status_id",
                sa.Integer(),
                sa.ForeignKey("article_status.id"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "article", "status_id"):
        op.drop_column("article", "status_id")

    if _has_column(inspector, "article", "content"):
        op.drop_column("article", "content")

    # Таблицу article_status не удаляем на downgrade: она может уже
    # существовать независимо от этой миграции (например, созданная
    # Base.metadata.create_all на старых установках) и использоваться
    # другим кодом.
