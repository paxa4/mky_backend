"""Add practice locations, expert conclusions, and reviewer role.

Revision ID: c8d1e4a7b2f6
Revises: b9c0d1e2f3a4
Create Date: 2026-11-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d1e4a7b2f6"
down_revision: Union[str, Sequence[str], None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("practice", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("practice", sa.Column("longitude", sa.Float(), nullable=True))
    op.create_check_constraint(
        "practice_location_pair_chk",
        "practice",
        "(latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL)",
    )

    op.create_table(
        "practice_conclusion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("practice_id", sa.Integer(), nullable=False),
        sa.Column("expert_user_id", sa.Integer(), nullable=True),
        sa.Column("expert_name", sa.String(length=300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["practice_id"], ["practice.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expert_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("practice_id", "expert_user_id", name="practice_conclusion_expert_unique"),
    )
    op.create_index(op.f("ix_practice_conclusion_id"), "practice_conclusion", ["id"], unique=False)
    op.create_index("practice_conclusion_practice_idx", "practice_conclusion", ["practice_id"], unique=False)

    role_table = sa.table(
        "user_role",
        sa.column("id", sa.Integer()),
        sa.column("role_name", sa.String(length=50)),
        sa.column("can_access_internal_docs", sa.Boolean()),
        sa.column("permissions", sa.JSON()),
    )
    bind = op.get_bind()
    role = bind.execute(
        sa.select(role_table.c.id, role_table.c.permissions).where(role_table.c.role_name == "practice_expert")
    ).first()
    if role is None:
        bind.execute(
            role_table.insert().values(
                role_name="practice_expert",
                can_access_internal_docs=False,
                permissions={"practice_expert": "edit"},
            )
        )
    else:
        permissions = dict(role.permissions or {})
        permissions["practice_expert"] = "edit"
        bind.execute(
            role_table.update()
            .where(role_table.c.id == role.id)
            .values(permissions=permissions)
        )


def downgrade() -> None:
    role_table = sa.table(
        "user_role",
        sa.column("id", sa.Integer()),
        sa.column("role_name", sa.String(length=50)),
    )
    users_table = sa.table(
        "users",
        sa.column("role_id", sa.Integer()),
    )
    bind = op.get_bind()
    bind.execute(
        role_table.delete().where(
            role_table.c.role_name == "practice_expert",
            ~sa.exists(sa.select(users_table.c.role_id).where(users_table.c.role_id == role_table.c.id)),
        )
    )

    op.drop_index("practice_conclusion_practice_idx", table_name="practice_conclusion")
    op.drop_index(op.f("ix_practice_conclusion_id"), table_name="practice_conclusion")
    op.drop_table("practice_conclusion")
    op.drop_constraint("practice_location_pair_chk", "practice", type_="check")
    op.drop_column("practice", "longitude")
    op.drop_column("practice", "latitude")
