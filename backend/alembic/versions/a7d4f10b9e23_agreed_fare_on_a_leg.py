"""A fare agreed for one run, rather than worked out from a standing rate.

Driver pay is per kilometre, which is right for the ordinary case and wrong
for the ones people actually ring about. A Kasaragod round trip is settled as
"twelve hundred for the run" before the lorry leaves; a short town job is "two
fifty and that is that". The rate card has no way to say either, so the office
either accepted a figure it had not agreed or kept the real number on paper —
and once the real number is on paper, the settlement screen is decoration.

Two amounts, because they are two different agreements:

    agreed_fare       replaces the distance calculation for this leg
    agreed_unloading  replaces the unloading share for this leg

Both nullable, and null means "work it out" — which is not the same as zero.
A leg with a fare of 0 is a run somebody has decided pays nothing for driving,
which is a real thing on a day a driver is being squared up some other way;
defaulting to it would silently stop paying everybody.

The note is not decoration either. An amount nobody can explain six weeks
later is an amount that gets queried, and "agreed with Shaji on the phone,
lorry was going back empty anyway" is the whole answer.

Revision ID: a7d4f10b9e23
Revises: f83d2b614a97
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7d4f10b9e23"
down_revision: str | None = "f83d2b614a97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "freight_legs", sa.Column("agreed_fare", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "freight_legs", sa.Column("agreed_unloading", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column("freight_legs", sa.Column("fare_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("freight_legs", "fare_note")
    op.drop_column("freight_legs", "agreed_unloading")
    op.drop_column("freight_legs", "agreed_fare")
