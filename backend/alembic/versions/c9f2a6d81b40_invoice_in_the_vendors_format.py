"""The invoice in the shape the vendor's accounts team already reads.

Target Express's own accountant issues these from Tally, and the document that
actually reaches Godrej groups the month by CHARGE HEAD, not by trip:

    Freight Charges Dost        24,271.00
    Freight Charges Ace         12,467.00
    Extra KM Charges          1,02,889.00
    Toll Charges                 2,150.00
    Unloading Charges            1,480.00
    Other Charges               14,525.00
    Detention Charges              750.00

Three facts in that document the system did not hold.

A FREIGHT CHARGE IS SPLIT BY VEHICLE TYPE. "Freight Charges Dost" and
"Freight Charges Ace" are separate lines because they are separately agreed,
and an accounts team checking the bill checks them separately. The type has to
be stored on the line rather than looked up, for the same reason every other
input to the arithmetic is: a lorry can be re-typed, and an invoice must
reprint as it was issued.

TOLL IS NOT TAXED. Their tax summary splits 1,56,382 at 2.5% + 2.5% against
2,150 at 0%, and the 2,150 is exactly the toll. It is money handed to a toll
booth and recharged at cost, not a service supplied. We were taxing it.

THE RATE BELONGS TO THE INVOICE. It was read off the division at print time,
so changing a division's GST rate would silently re-rate every invoice ever
issued against it the next time one was opened.

Revision ID: c9f2a6d81b40
Revises: b8e1c5a7420f
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9f2a6d81b40"
down_revision: str | None = "b8e1c5a7420f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reimbursements recharged at cost. Nil on every invoice already issued,
    # which is true of them: they were taxed, and their stored totals stay as
    # they were sent.
    op.add_column(
        "vendor_invoices",
        sa.Column(
            "zero_rated_value", sa.Numeric(14, 2), server_default="0", nullable=False
        ),
    )
    # The rate this invoice was raised at, rather than whatever the division
    # says today.
    op.add_column(
        "vendor_invoices",
        sa.Column(
            "gst_rate_percent", sa.Numeric(5, 2), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "vendor_invoice_lines", sa.Column("vehicle_type", sa.String(length=64), nullable=True)
    )

    # Old invoices keep the rate they were issued at, taken from the division
    # they were raised against. Leaving them at zero would make every reprint
    # claim the work had been untaxed.
    op.execute(
        """
        UPDATE vendor_invoices
           SET gst_rate_percent = COALESCE(
                 (SELECT d.gst_rate_percent
                    FROM vendor_divisions d
                   WHERE d.id = vendor_invoices.vendor_division_id),
                 0)
        """
    )


def downgrade() -> None:
    op.drop_column("vendor_invoice_lines", "vehicle_type")
    op.drop_column("vendor_invoices", "gst_rate_percent")
    op.drop_column("vendor_invoices", "zero_rated_value")
