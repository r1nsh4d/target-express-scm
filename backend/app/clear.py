"""Clear the day-to-day records and keep the setup.

After a demo — or after a month of trialling — what you want is not an empty
database. Rebuilding from nothing means re-entering every vendor, division,
warehouse, rate card, customer, vehicle and driver, which is most of a day's
work and the part nobody wants to do twice.

So this draws a line between two kinds of data:

  SETUP, which is kept. Who you work for, what you charge them, where you
  deliver, what you drive, who drives it, and who can sign in. These were
  entered once and are still true tomorrow.

  RECORDS, which go. Freights, bills, boxes, invoices, settlements, expenses,
  advances, returns, GPS trails, tracking links. These describe work that
  happened, and clearing them is exactly what "start from today" means.

Deleted in dependency order inside one transaction, so a failure anywhere
leaves the database as it was rather than half-emptied with foreign keys
dangling.

    python -m app.clear --dry-run    say what would go, change nothing
    python -m app.clear --yes        do it
"""

from __future__ import annotations

import sys

from sqlalchemy import func, select

from app.db.session import SessionLocal

# Children first. A list rather than a graph walk, because the order is a
# deliberate statement about this schema and should be read, not inferred.
RECORD_TABLES = [
    # The box and everything hanging off a delivery
    "vehicle_pings",
    "tracking_sessions",
    "location_change_requests",
    "odometer_corrections",
    "boxes",
    "consignments",
    # Money
    "vendor_invoice_lines",
    "vendor_invoices",
    "freight_payouts",
    "settlements",
    "advances",
    "trip_expenses",
    # The trip itself
    "freight_points",
    "freight_legs",
    "freights",
    # Who asked to work with us
    "enquiries",
    # The trail of who changed what, which describes the records above
    "audit_logs",
]

# Named so the list can be read as a promise rather than worked out by
# subtracting one list from another.
KEPT_TABLES = [
    "users",
    "drivers",
    "driver_pay_terms",
    "vehicles",
    "vehicle_types",
    "vehicle_owners",
    "vehicle_hire_terms",
    "labour",
    "market_vehicles",
    "vendors",
    "vendor_divisions",
    "vendor_warehouses",
    "goods_categories",
    "consignees",
    "rate_cards",
    "unloading_item_rates",
    "route_presets",
    "route_preset_points",
]


def counts(db) -> dict[str, int]:
    from app.db.base import Base

    out: dict[str, int] = {}
    for name in RECORD_TABLES:
        table = Base.metadata.tables[name]
        out[name] = int(db.scalar(select(func.count()).select_from(table)) or 0)
    return out


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    dry_run = "--dry-run" in args
    confirmed = "--yes" in args

    from app.db.base import Base
    import app.models  # noqa: F401

    db = SessionLocal()
    try:
        before = counts(db)
        total = sum(before.values())

        print("Records that would be cleared:")
        for name, n in before.items():
            if n:
                print(f"  {name:<28}{n:>8}")
        if not total:
            print("  (nothing — the records are already clear)")

        print()
        print("Kept, untouched:")
        for name in KEPT_TABLES:
            table = Base.metadata.tables[name]
            n = int(db.scalar(select(func.count()).select_from(table)) or 0)
            if n:
                print(f"  {name:<28}{n:>8}")

        if dry_run:
            print()
            print("Dry run — nothing was changed.")
            return 0

        if not total:
            return 0

        if not confirmed:
            print()
            print(f"This would delete {total} rows. Re-run with --yes to do it.")
            return 1

        # One transaction. A failure half way leaves the database as it was,
        # rather than with bills whose freight no longer exists.
        print()
        for name in RECORD_TABLES:
            table = Base.metadata.tables[name]
            result = db.execute(table.delete())
            if result.rowcount:
                print(f"  cleared {name} ({result.rowcount})")
        db.commit()

        print()
        print(f"Cleared {total} records. Vendors, rates, customers, vehicles,")
        print("drivers and logins are untouched.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
