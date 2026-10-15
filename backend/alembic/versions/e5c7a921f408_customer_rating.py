"""What the customer said about the delivery.

The only account of a delivery that does not come from the people who made it.
A driver who is quick and careful and one who leaves cartons in the rain look
identical in a box count, and the office has no other way to tell them apart.

All three nullable. Most people will not bother, and a default rating of 3
would be an opinion nobody held.

Revision ID: e5c7a921f408
Revises: d41b8e73a5c2
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5c7a921f408"
down_revision: str | None = "d41b8e73a5c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("freight_points", sa.Column("customer_rating", sa.Integer(), nullable=True))
    op.add_column("freight_points", sa.Column("customer_remarks", sa.Text(), nullable=True))
    op.add_column(
        "freight_points", sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("freight_points", "rated_at")
    op.drop_column("freight_points", "customer_remarks")
    op.drop_column("freight_points", "customer_rating")
