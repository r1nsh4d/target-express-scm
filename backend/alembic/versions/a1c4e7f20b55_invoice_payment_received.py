"""Record what actually came in against an invoice.

PAID on its own says a payment happened and nothing else: not when, not how
much, not against which reference. That is enough to stop chasing an invoice
and not enough to reconcile it against a bank statement, which is what "money
in" has to mean.

`amount_received` is deliberately separate from `total` and is often SMALLER.
Transport vendors deduct TDS at source, so a 92,478.40 invoice is settled by
91,553.62 and the balance turns up later as a TDS credit. Writing the invoice
total into the receipt would overstate money in and leave the reconciliation
short with nothing to explain the gap.

All four columns are nullable: an invoice that has not been paid has no payment
date and no amount, and 0.00 would be a lie about a receipt that never
happened.

Revision ID: a1c4e7f20b55
Revises: 0b810cf7f608
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e7f20b55"
down_revision: str | None = "0b810cf7f608"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vendor_invoices", sa.Column("paid_on", sa.Date(), nullable=True))
    op.add_column(
        "vendor_invoices", sa.Column("amount_received", sa.Numeric(14, 2), nullable=True)
    )
    op.add_column(
        "vendor_invoices", sa.Column("payment_mode", sa.String(length=24), nullable=True)
    )
    op.add_column(
        "vendor_invoices",
        sa.Column("payment_reference", sa.String(length=120), nullable=True),
    )
    # Money in is read by date far more often than by anything else.
    op.create_index(
        "ix_vendor_invoices_paid_on", "vendor_invoices", ["paid_on"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_vendor_invoices_paid_on", table_name="vendor_invoices")
    op.drop_column("vendor_invoices", "payment_reference")
    op.drop_column("vendor_invoices", "payment_mode")
    op.drop_column("vendor_invoices", "amount_received")
    op.drop_column("vendor_invoices", "paid_on")
