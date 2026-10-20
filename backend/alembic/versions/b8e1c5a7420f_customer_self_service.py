"""A contact person, and a link the customer fills in themselves.

TWO THINGS A CUSTOMER RECORD WAS MISSING.

A contact person. "Kottayam Furniture Mart" is a shop and somebody answers its
phone; "Rinshad Km" is a person and the same field means something different.
A distributor has a purchase manager whose name is what the driver asks for at
the gate, and there was nowhere to write it — so it went in the delivery notes
if it went anywhere.

A way to be completed by the person who knows. The warehouse admin entering a
morning's bills types a name, a mobile and a town, because that is all he has
and all he has time for. The address, the landmark, the floor and the pin come
from the customer, and the only practical way to ask is to send them a link.

So a consignee carries a one-use token and the state of that request: when it
was sent, when they filled it in, and what they said. The token is random,
expires, and reaches exactly one record — it is a link to correct your own
delivery address, not a login.

Revision ID: b8e1c5a7420f
Revises: a7d4f10b9e23
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8e1c5a7420f"
down_revision: str | None = "a7d4f10b9e23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "consignees", sa.Column("contact_person", sa.String(length=160), nullable=True)
    )
    op.add_column(
        "consignees", sa.Column("details_token", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "consignees",
        sa.Column("details_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "consignees",
        sa.Column("details_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "consignees",
        sa.Column("details_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_consignees_details_token", "consignees", ["details_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_consignees_details_token", table_name="consignees")
    op.drop_column("consignees", "details_completed_at")
    op.drop_column("consignees", "details_requested_at")
    op.drop_column("consignees", "details_token_expires_at")
    op.drop_column("consignees", "details_token")
    op.drop_column("consignees", "contact_person")
