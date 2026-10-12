"""What the driver is paid for unloading each article.

Unloading has two prices for the same chair: what the vendor is charged and
what the driver is paid for carrying it. The difference is Target Express's
margin on unloading, and until now only the vendor's side existed — the driver
got a percentage, which cannot express "a chair earns him 30 and a wardrobe
earns him 80".

Both sides live on one row deliberately. They are the same commercial decision
taken twice, and splitting them into two tables makes it possible to raise one
and forget the other, which is how a margin silently becomes a loss. One row
also means they are versioned together, so re-pricing an old trip reproduces
both figures as they stood that day.

Zero is a real answer: a division whose drivers are paid a percentage leaves
these at zero and the older arrangement applies. That is why they carry a
server_default of 0 rather than being nullable — the table is populated, and a
NOT NULL column added without a default stops an ALTER dead.

Revision ID: b73f1d92c408
Revises: a1c4e7f20b55
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b73f1d92c408"
down_revision: str | None = "a1c4e7f20b55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "unloading_item_rates",
        sa.Column(
            "driver_base_rate",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "unloading_item_rates",
        sa.Column(
            "driver_per_floor_rate",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("unloading_item_rates", "driver_per_floor_rate")
    op.drop_column("unloading_item_rates", "driver_base_rate")
