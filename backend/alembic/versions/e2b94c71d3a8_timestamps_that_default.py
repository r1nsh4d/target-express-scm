"""Four tables nothing could be inserted into.

Every model inherits `created_at` and `updated_at` declared NOT NULL with
`server_default=func.now()`, so SQLAlchemy leaves them out of an INSERT and
lets the database fill them. The initial schema created all thirty-five
tables that way. Every migration since that CREATED a table declared the
columns NOT NULL and forgot the default — so Postgres had a NOT NULL column
with no DEFAULT, the INSERT omitted it, and the row was refused.

    roles, role_capabilities, role_screens   nothing could be saved, so the
                                             Roles screen 500ed on open
    point_unloading_items                    the driver's unloading log

The second one is the "Something went wrong" a driver was seeing at the door.
He ticked his articles, pressed save, and the server refused the row with a
NotNullViolation — which reaches a phone as a 500 with no detail on it, and a
phone with no detail says "Something went wrong".

It never showed up in the suite because the tests build SQLite from the MODEL
metadata, where the default is present, and never from these migrations. The
rule that would have caught it is now in test_schema_rules.

Existing rows cannot exist — the inserts all failed — but the backfill is
there anyway, because a column being made NOT NULL DEFAULT over data somebody
loaded by hand should not be the thing that fails next.

Revision ID: e2b94c71d3a8
Revises: d1a7e3f94c25
Create Date: 2026-10-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e2b94c71d3a8"
down_revision: str | None = "d1a7e3f94c25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("roles", "role_capabilities", "role_screens", "point_unloading_items")


def upgrade() -> None:
    for table in TABLES:
        for column in ("created_at", "updated_at"):
            op.execute(f"UPDATE {table} SET {column} = now() WHERE {column} IS NULL")
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT now()")


def downgrade() -> None:
    for table in TABLES:
        for column in ("created_at", "updated_at"):
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
