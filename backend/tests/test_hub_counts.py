"""The numbers on the hub tiles.

The rail is eight entries now and everything else is a tile inside one of
them. A tile carries a count, because "Vehicles 11" is scannable in a way that
"Vehicles" is not, and one request feeds all of them.

Three things can go wrong, and all three are silent:

  * The tile asks for a key the endpoint does not return. Nothing appears, no
    error anywhere, and it looks like there are simply no records. So the last
    test here reads the tile definitions out of the frontend and checks every
    key it asks for is one this endpoint answers.
  * A count includes retired rows, and the tile says eleven lorries when nine
    are on the road.
  * A tile that should draw attention stops doing so. `consignments_waiting`
    is the one worth having: a bill with no vehicle against it cannot be
    labelled or delivered, and no other screen says so.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.tables(
    "users",
    "roles",
    "enquiries",
    "goods_categories",
    "vendors",
    "vendor_divisions",
    "vendor_warehouses",
    "consignees",
    "vehicle_types",
    "vehicle_owners",
    "vehicles",
    "market_vehicles",
    "drivers",
    "labour",
    "freights",
    "freight_points",
    "freight_legs",
    "consignments",
    "boxes",
    "vendor_invoices",
    "trip_expenses",
    "advances",
    "rate_cards",
    "unloading_item_rates",
    "route_presets",
)


def test_an_empty_system_answers_with_zeroes(client, auth):
    """Not an error, and not an empty object — zeroes."""
    res = client.get("/api/hub-counts", headers=auth)
    assert res.status_code == 200

    counts = res.json()
    assert counts["vehicles"] == 0
    assert counts["consignments"] == 0

    # Everything except the admin asking the question, who is a user.
    assert counts["users"] == 1
    assert set(counts.values()) == {0, 1}
    assert sum(counts.values()) == 1


def test_a_retired_vehicle_is_not_counted(client, auth):
    """Retiring is how this application deletes, so the tile has to respect it."""
    from app.db.session import SessionLocal
    from app.models.fleet import Vehicle

    db = SessionLocal()
    try:
        db.add(Vehicle(registration_no="KL07AA1111", is_active=True))
        db.add(Vehicle(registration_no="KL07AA2222", is_active=False))
        db.commit()
    finally:
        db.close()

    counts = client.get("/api/hub-counts", headers=auth).json()
    assert counts["vehicles"] == 1


def test_a_bill_with_no_vehicle_shows_as_waiting(client, auth):
    """The one count on the screen that is a job rather than a total."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.consignment import Consignment
    from app.models.vendor import Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()
    try:
        vendor = Vendor(name="Godrej")
        db.add(vendor)
        db.flush()
        division = VendorDivision(vendor_id=vendor.id, name="OCP", code="OCP")
        warehouse = VendorWarehouse(vendor_id=vendor.id, name="Ernakulam", code="EKM")
        consignee = Consignee(name="Kottayam Furniture")
        db.add_all([division, warehouse, consignee])
        db.flush()
        db.add(
            Consignment(
                vendor_division_id=division.id,
                warehouse_id=warehouse.id,
                consignee_id=consignee.id,
                vendor_bill_no="GJ/1001",
                bill_date=date.today(),
                # Not on a freight yet. This is the state the tile exists for.
                freight_point_id=None,
            )
        )
        db.commit()
    finally:
        db.close()

    counts = client.get("/api/hub-counts", headers=auth).json()
    assert counts["consignments"] == 1
    assert counts["consignments_waiting"] == 1


def test_a_driver_cannot_read_the_office_counts(client, auth):
    """He has his own screens. This one totals the whole business."""
    from app.core.security import create_access_token
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.user import User

    db = SessionLocal()
    try:
        driver = User(
            full_name="Shaji",
            phone="9000000001",
            role=UserRole.DRIVER,
            hashed_password="x",
            is_active=True,
        )
        db.add(driver)
        db.commit()
        token = create_access_token(str(driver.id), driver.role)
    finally:
        db.close()

    res = client.get("/api/hub-counts", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_every_tile_asks_for_a_key_this_endpoint_returns(client, auth):
    """The failure this pairing is prone to, caught where it is cheap.

    A tile naming a count the endpoint does not return shows no number at all,
    which reads as "there is nothing here" rather than as a bug. Nothing else
    in either half of the codebase connects the two names, so this does.
    """
    hubs = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "hubs.tsx"
    if not hubs.exists():  # pragma: no cover - backend-only checkout
        pytest.skip("frontend not present")

    wanted = set(re.findall(r"count:\s*'([a-z_]+)'", hubs.read_text(encoding="utf-8")))
    assert wanted, "no tile counts found — has the regex drifted from the source?"

    answered = set(client.get("/api/hub-counts", headers=auth).json())
    assert wanted <= answered, f"tiles ask for counts nobody returns: {wanted - answered}"
