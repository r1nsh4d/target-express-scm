"""Logins for people who are not Target Express.

Two kinds, and what makes them different from every login before them is that
they belong to somebody OUTSIDE the company:

    A VENDOR raises its own freights, reads the rates it agreed, and sees what
    it has been billed and what it owes — for its own business and nothing
    else. Godrej must never see a line of Usha's.

    A VEHICLE OWNER hires his lorry to Target Express and wants to know what
    it earned and what he has already drawn. His driver is paid by him, not by
    us, so the money is his question and not the driver's.

So a user can be tied to one vendor or one vehicle owner, and every endpoint
behind those logins filters on that tie. The column is the whole security
boundary: without it there is nothing to scope a query by, and "show me my
freights" becomes "show me the freights".

Both are nullable because every existing login is a Target Express one and
belongs to neither.

Revision ID: d1a7e3f94c25
Revises: c9f2a6d81b40
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1a7e3f94c25"
down_revision: str | None = "c9f2a6d81b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("vendor_id", sa.UUID(), nullable=True))
    op.add_column("users", sa.Column("vehicle_owner_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_users_vendor", "users", "vendors", ["vendor_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_users_vehicle_owner",
        "users",
        "vehicle_owners",
        ["vehicle_owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_vendor_id", "users", ["vendor_id"])
    op.create_index("ix_users_vehicle_owner_id", "users", ["vehicle_owner_id"])


def downgrade() -> None:
    op.drop_index("ix_users_vehicle_owner_id", table_name="users")
    op.drop_index("ix_users_vendor_id", table_name="users")
    op.drop_constraint("fk_users_vehicle_owner", "users", type_="foreignkey")
    op.drop_constraint("fk_users_vendor", "users", type_="foreignkey")
    op.drop_column("users", "vehicle_owner_id")
    op.drop_column("users", "vendor_id")
