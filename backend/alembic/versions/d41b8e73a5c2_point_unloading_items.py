"""What the driver actually carried in at each stop.

The vendor's unloading charge was worked out from the BOXES on the bill, which
is a guess at what happened: the bill says five chairs, four came off the
lorry, one was refused at the door, and the sheet charged for five anyway. The
man who carried them knows, and he is standing there with a phone.

So he logs it, and this is what the unloading sheet is priced from when it
exists. The boxes stay as the fallback for a stop where nobody logged anything,
because a charge of zero because a driver forgot is worse than a charge from
the paperwork.

The item name is stored rather than looked up. Rate cards are versioned and
never edited, but an article can be renamed, and a sheet reprinted next year
should say what the driver was shown at the door.

Revision ID: d41b8e73a5c2
Revises: c92a4e1b7d36
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d41b8e73a5c2"
down_revision: str | None = "c92a4e1b7d36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "point_unloading_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("freight_point_id", sa.UUID(), nullable=False),
        sa.Column("item_code", sa.String(length=48), nullable=False),
        sa.Column("item_name", sa.String(length=160), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["freight_point_id"], ["freight_points.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        # One row per article per stop. Logging the same article twice is a
        # double charge to the vendor and double pay to the driver, so it is
        # refused by the table rather than by a check somebody might forget.
        sa.UniqueConstraint(
            "freight_point_id", "item_code", name="uq_point_unloading_point_item"
        ),
    )
    op.create_index(
        "ix_point_unloading_items_freight_point_id",
        "point_unloading_items",
        ["freight_point_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_point_unloading_items_freight_point_id", table_name="point_unloading_items"
    )
    op.drop_table("point_unloading_items")
