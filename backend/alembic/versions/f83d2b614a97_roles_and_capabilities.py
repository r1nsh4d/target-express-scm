"""Roles somebody can make, instead of six compiled into the application.

The six built-in roles are seeded by the application rather than here, because
their capabilities live in code — core.privileges describes them completely,
and a migration that also described them would be a second copy to keep in
step. The tables are created here; the rows appear the first time anybody
opens the Roles screen.

user.role_id is nullable and SET NULL on delete. The enum column stays as the
fallback, so every existing check still has an answer and nothing had to be
rewritten to make roles configurable.

Revision ID: f83d2b614a97
Revises: e5c7a921f408
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f83d2b614a97"
down_revision: str | None = "e5c7a921f408"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default, not just nullable=False. SQLAlchemy leaves these
    # out of an INSERT and lets the database fill them, so a NOT NULL
    # column with no DEFAULT refuses every row. Added after four tables
    # shipped without it; `e2b94c71d3a8` repairs databases already built
    # from this file, and this fixes the ones built from it next.
    op.create_table(
        "roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("base_role", sa.String(length=24), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_role_name"),
    )

    op.create_table(
        "role_capabilities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("capability", sa.String(length=48), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Granting the same thing twice is not a different grant.
        sa.UniqueConstraint("role_id", "capability", name="uq_role_capability"),
    )
    op.create_index(
        "ix_role_capabilities_role_id", "role_capabilities", ["role_id"]
    )

    op.create_table(
        "role_screens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("screen", sa.String(length=48), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "screen", name="uq_role_screen"),
    )
    op.create_index("ix_role_screens_role_id", "role_screens", ["role_id"])

    op.add_column("users", sa.Column("role_id", sa.UUID(), nullable=True))
    op.create_index("ix_users_role_id", "users", ["role_id"])
    op.create_foreign_key(
        "fk_users_role_id_roles", "users", "roles", ["role_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_role_id_roles", "users", type_="foreignkey")
    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_column("users", "role_id")
    op.drop_index("ix_role_screens_role_id", table_name="role_screens")
    op.drop_table("role_screens")
    op.drop_index("ix_role_capabilities_role_id", table_name="role_capabilities")
    op.drop_table("role_capabilities")
    op.drop_table("roles")
