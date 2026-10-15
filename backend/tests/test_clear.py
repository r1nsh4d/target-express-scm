"""Clearing the records without losing the setup.

After a demo, what you want is not an empty database. Rebuilding from nothing
means re-entering every vendor, division, warehouse, rate card, customer,
vehicle and driver — most of a day's work, and the part nobody wants to do
twice.

So the line between the two kinds of data has to be exactly right, and it has
to stay right as tables are added. A table that nobody classified is the real
risk: it would silently survive a clear and leave last month's work in a
database somebody believes is empty.
"""

from app.clear import KEPT_TABLES, RECORD_TABLES
from app.db.base import Base
import app.models  # noqa: F401


def test_every_table_is_classified():
    """The one that matters as the schema grows. A new table nobody put in a
    list would survive a clear unnoticed."""
    unclassified = set(Base.metadata.tables) - set(RECORD_TABLES) - set(KEPT_TABLES)
    assert not unclassified, (
        f"These tables are in neither list, so a clear would silently leave them: "
        f"{sorted(unclassified)}"
    )


def test_no_table_is_in_both_lists():
    assert not set(RECORD_TABLES) & set(KEPT_TABLES)


def test_both_lists_name_real_tables():
    """A typo would mean a table nobody clears and nobody notices."""
    invented = (set(RECORD_TABLES) | set(KEPT_TABLES)) - set(Base.metadata.tables)
    assert not invented, f"not real tables: {sorted(invented)}"


def test_the_things_that_must_survive():
    """Named explicitly rather than inferred, because this list is the promise
    the command makes."""
    for table in (
        "users",
        "vendors",
        "vendor_divisions",
        "rate_cards",
        "unloading_item_rates",
        "consignees",
        "vehicles",
        "drivers",
        "driver_pay_terms",
        "route_presets",
    ):
        assert table in KEPT_TABLES, f"{table} would be destroyed"


def test_the_things_that_must_go():
    for table in (
        "freights",
        "freight_points",
        "consignments",
        "boxes",
        "vendor_invoices",
        "vendor_invoice_lines",
        "settlements",
        "freight_payouts",
        "trip_expenses",
        "vehicle_pings",
        "tracking_sessions",
    ):
        assert table in RECORD_TABLES, f"{table} would survive a clear"


def test_children_are_deleted_before_their_parents():
    """Deleting a freight before its points would fail on the foreign key, and
    the whole clear would roll back."""
    order = {name: i for i, name in enumerate(RECORD_TABLES)}
    for child, parent in [
        ("boxes", "consignments"),
        ("consignments", "freight_points"),
        ("point_unloading_items", "freight_points"),
        ("vendor_invoice_lines", "vendor_invoices"),
        ("freight_points", "freights"),
        ("freight_legs", "freights"),
        ("vehicle_pings", "freights"),
        ("tracking_sessions", "freight_points"),
        ("freight_payouts", "settlements"),
        ("trip_expenses", "freights"),
    ]:
        assert order[child] < order[parent], f"{child} must be cleared before {parent}"
