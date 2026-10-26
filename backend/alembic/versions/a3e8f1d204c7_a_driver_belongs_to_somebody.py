"""Whose man is this.

Two kinds of lorry and two kinds of driver, and only the lorries were
modelled:

    A COMPANY LORRY is driven by a company driver. Target Express pays him,
    by the kilometre, plus the unloading cash he hands over at the door.

    AN OUTSIDE LORRY belongs to somebody who may drive it himself or may
    send a man. Target Express pays the OWNER for the lorry and what it
    carried in; the man at the wheel is paid by the owner, and what he is
    paid is not our business.

A vehicle has always known whose it is. A driver has not. So a driver who is
Ibrahim's man and a driver who is ours looked the same in every list, and
there was no way to ask "who are Ibrahim's drivers" — which is the question
behind giving one of them a login, and behind an owner reading what his own
lorries did.

`engagement` carried a hint of it — OWN_STAFF against ATTACHED_TO_HIRED_
VEHICLE — but it says only that a man drives somebody else's lorry, not
WHOSE. One owner with four lorries and three drivers is an ordinary
arrangement and that column cannot describe it.

NULL means a Target Express driver, which is what every existing row is: the
only hired driver on file is Basheer, and whose man he is was not recorded
anywhere to migrate from. It is one field on one row in the office, not a
re-seed.

Revision ID: a3e8f1d204c7
Revises: f4c0a81e76b2
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3e8f1d204c7"
down_revision: str | None = "f4c0a81e76b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("drivers", sa.Column("vehicle_owner_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_drivers_vehicle_owner",
        "drivers",
        "vehicle_owners",
        ["vehicle_owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_drivers_vehicle_owner_id", "drivers", ["vehicle_owner_id"])


def downgrade() -> None:
    op.drop_index("ix_drivers_vehicle_owner_id", table_name="drivers")
    op.drop_constraint("fk_drivers_vehicle_owner", "drivers", type_="foreignkey")
    op.drop_column("drivers", "vehicle_owner_id")
