"""Cartons that came back.

The box reconciliation already counted returns — loaded minus delivered minus
returned is what says whether anything is actually missing. There was simply no
way to record one, so every carton that came back counted as "unaccounted",
which is the alarm that should be reserved for a box nobody can find.

Three nullable columns on the box: when it came back, who recorded it, and why.
The reason is the one that matters. "12 boxes came back" is a number nobody can
act on; "4 refused by Anand Agencies, wrong model" is something the vendor can
be told and the warehouse can put right.

Nullable, because almost every box in the table will never be returned and a
default here would be a lie about a carton that was delivered normally.

Revision ID: c92a4e1b7d36
Revises: b73f1d92c408
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c92a4e1b7d36"
down_revision: str | None = "b73f1d92c408"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "boxes", sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("boxes", sa.Column("returned_by_id", sa.UUID(), nullable=True))
    op.add_column("boxes", sa.Column("return_reason", sa.Text(), nullable=True))

    op.create_index("ix_boxes_returned_at", "boxes", ["returned_at"], unique=False)
    op.create_foreign_key(
        "fk_boxes_returned_by_id_users",
        "boxes",
        "users",
        ["returned_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_boxes_returned_by_id_users", "boxes", type_="foreignkey")
    op.drop_index("ix_boxes_returned_at", table_name="boxes")
    op.drop_column("boxes", "return_reason")
    op.drop_column("boxes", "returned_by_id")
    op.drop_column("boxes", "returned_at")
