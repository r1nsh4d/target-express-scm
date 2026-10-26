"""A hired lorry is paid for as a lorry, not as a lorry plus a man.

Target Express hires a vehicle from outside, and after the run it pays the
OWNER one amount: the hire and the unloading together. Whether the owner
drives it himself or sends a man, and what he pays that man, is his
arrangement — it does not reach Target Express's books at all.

The terms defaulted the other way. `unloading_paid_to_owner` was False, so
the unloading went to the DRIVER on a hired lorry, which is right for an
OWNED one — there the driver is ours and the cash he handed to the labourers
is ours to reimburse — and wrong for a hired one, where it put us in the
middle of an arrangement we are not part of and produced two settlements for
one hire.

Existing rows are moved with the default, because they were all written
under the old assumption and none of them was a deliberate choice to pay a
hired driver directly. The flag stays, so that choice can still be made and
recorded where it is actually made.

Revision ID: f4c0a81e76b2
Revises: e2b94c71d3a8
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4c0a81e76b2"
down_revision: str | None = "e2b94c71d3a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "vehicle_hire_terms",
        "unloading_paid_to_owner",
        server_default=sa.text("true"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE vehicle_hire_terms SET unloading_paid_to_owner = true "
        "WHERE unloading_paid_to_owner = false"
    )


def downgrade() -> None:
    op.alter_column(
        "vehicle_hire_terms",
        "unloading_paid_to_owner",
        server_default=sa.text("false"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
