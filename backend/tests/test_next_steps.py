"""Telling people what to do next.

The people using this have no software background, and the commonest failure is
not that a screen is confusing on its own — it is that nothing anywhere says
which screen to be on. A bill sits unassigned, a freight is never dispatched, a
finished trip is never invoiced, and each is invisible until somebody happens
to look at the right list.

Two rules these tests hold:

  * A suggestion appears only when there is something real behind it. Advice
    that is always on screen is advice people learn to ignore, so an empty
    system says so rather than inventing a task.
  * The most expensive thing to leave comes first. Money earned and not asked
    for outranks an afternoon's housekeeping.
"""

from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.tables(
    "users",
    "goods_categories",
    "vendors",
    "vendor_divisions",
    "vendor_warehouses",
    "consignees",
    "vehicle_owners",
    "vehicles",
    "drivers",
    "freights",
    "freight_points",
    "freight_legs",
    "consignments",
    "boxes",
    "vendor_invoices",
    "vendor_invoice_lines",
    "enquiries",
)


@pytest.fixture()
def world(client, auth):
    """The pieces, with nothing yet to do."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, GeoConfidence
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()
    category = GoodsCategory(name="Appliance", code="APPLIANCE")
    vendor = Vendor(name="Godrej", payment_terms_days=30, is_active=True)
    db.add_all([category, vendor])
    db.flush()
    division = VendorDivision(
        vendor_id=vendor.id,
        goods_category_id=category.id,
        name="Godrej Appliance Spare",
        code="GODREJ-SPARE",
        invoice_series="191",
        is_active=True,
    )
    warehouse = VendorWarehouse(vendor_id=vendor.id, name="Kochi godown", code="KOCHI")
    db.add_all([division, warehouse])
    db.flush()
    owner = VehicleOwner(name="Target Express", phone="9000000043", is_active=True)
    db.add(owner)
    db.flush()
    vehicle = Vehicle(
        owner_id=owner.id, registration_no="KL07CW3317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Rajesh K", phone="9000000034", is_active=True)
    consignee = Consignee(
        name="Kannur Distribution Centre",
        type=ConsigneeType.DISTRIBUTION_CENTER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([vehicle, driver, consignee])
    db.commit()
    data = {
        "division": str(division.id),
        "warehouse": str(warehouse.id),
        "consignee": str(consignee.id),
        "vehicle": str(vehicle.id),
        "driver": str(driver.id),
    }
    db.close()
    return data


def _steps(client, auth) -> dict:
    res = client.get("/api/next-steps", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _keys(client, auth) -> list[str]:
    return [s["key"] for s in _steps(client, auth)["steps"]]


def _make_freight(world, status, *, days_ago=0, with_leg=False):
    from app.db.session import SessionLocal
    from app.models.freight import Freight, FreightLeg, FreightPoint

    db = SessionLocal()
    trip_day = date.today() - timedelta(days=days_ago)
    freight = Freight(
        trip_no=f"Y2600{days_ago:02d}{status[:2]}",
        trip_date=trip_day,
        vendor_division_id=world["division"],
        warehouse_id=world["warehouse"],
        status=status,
        point_count=1,
        total_km=100,
    )
    db.add(freight)
    db.flush()
    db.add(FreightPoint(freight_id=freight.id, sequence=1, consignee_id=world["consignee"]))
    if with_leg:
        db.add(
            FreightLeg(
                freight_id=freight.id,
                sequence=1,
                vehicle_id=world["vehicle"],
                driver_id=world["driver"],
                start_odometer=1000,
            )
        )
    db.commit()
    out = str(freight.id)
    db.close()
    return out


# ---------------------------------------------------------------------------
# Nothing to do
# ---------------------------------------------------------------------------


def test_an_empty_system_says_so(client, world, auth):
    """A blank space reads as a screen that has not loaded. Advice that is
    always on is advice people learn to ignore, so there is none here."""
    body = _steps(client, auth)
    assert body["all_clear"] is True
    assert body["steps"] == []


# ---------------------------------------------------------------------------
# Each thing worth saying
# ---------------------------------------------------------------------------


def test_a_finished_trip_nobody_billed(client, world, auth):
    _make_freight(world, "COMPLETED", days_ago=10)
    steps = _steps(client, auth)["steps"]

    step = next(s for s in steps if s["key"] == "unbilled")
    assert "Bill 1 finished trip" in step["title"]
    assert "10 days ago" in step["detail"]
    assert step["to"] == "/invoices"
    assert step["urgency"] == "now", "older than a week is money not asked for"


def test_a_trip_finished_today_is_not_urgent(client, world, auth):
    _make_freight(world, "COMPLETED")
    step = next(s for s in _steps(client, auth)["steps"] if s["key"] == "unbilled")
    assert step["urgency"] == "soon"


def test_a_loaded_trip_that_could_be_moving(client, world, auth):
    _make_freight(world, "PLANNED", with_leg=True)
    step = next(s for s in _steps(client, auth)["steps"] if s["key"] == "dispatch")
    assert "Dispatch 1 loaded trip" in step["title"]
    assert step["urgency"] == "now"


def test_a_trip_with_no_vehicle_is_not_offered_for_dispatch(client, world, auth):
    """There is nothing to dispatch without a driver and a lorry."""
    _make_freight(world, "PLANNED", with_leg=False)
    assert "dispatch" not in _keys(client, auth)


def test_a_stop_with_no_bills_on_it(client, world, auth):
    _make_freight(world, "PLANNED")
    step = next(s for s in _steps(client, auth)["steps"] if s["key"] == "empty_stops")
    assert "Put bills on 1 empty stop" in step["title"]


def test_a_trip_still_showing_as_out(client, world, auth):
    """Out for days means the closing odometer was never entered — and the trip
    cannot be billed until it is."""
    _make_freight(world, "IN_TRANSIT", days_ago=5)
    step = next(s for s in _steps(client, auth)["steps"] if s["key"] == "stale")
    assert step["urgency"] == "now"
    assert "cannot be billed" in step["detail"]


def test_a_trip_out_since_yesterday_is_not_flagged(client, world, auth):
    """Normal. A run can take two days."""
    _make_freight(world, "IN_TRANSIT", days_ago=1)
    assert "stale" not in _keys(client, auth)


def test_bills_waiting_for_a_lorry(client, world, auth):
    from app.db.session import SessionLocal
    from app.models.consignment import Consignment

    db = SessionLocal()
    db.add(
        Consignment(
            vendor_division_id=world["division"],
            warehouse_id=world["warehouse"],
            consignee_id=world["consignee"],
            vendor_bill_no="GDJ/9500",
            bill_date=date.today(),
            declared_box_count=3,
        )
    )
    db.commit()
    db.close()

    step = next(s for s in _steps(client, auth)["steps"] if s["key"] == "unassigned")
    assert "Put 1 bill on a freight" in step["title"]
    assert step["to"] == "/day-sheet"


def test_a_new_enquiry(client, world, auth):
    from app.db.session import SessionLocal
    from app.models.enquiry import Enquiry

    db = SessionLocal()
    db.add(Enquiry(
            company_name="Vadakara Traders",
            contact_name="Suresh",
            phone="9000098765",
            message="Need a lorry",
        ))
    db.commit()
    db.close()

    step = next(s for s in _steps(client, auth)["steps"] if s["key"] == "enquiries")
    assert step["urgency"] == "now"
    assert "one working day" in step["detail"]


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


def test_the_urgent_things_come_first(client, world, auth):
    """Money earned and not asked for outranks an afternoon's housekeeping."""
    from app.db.session import SessionLocal
    from app.models.consignment import Consignment

    _make_freight(world, "COMPLETED", days_ago=30)  # urgent
    db = SessionLocal()
    db.add(
        Consignment(
            vendor_division_id=world["division"],
            warehouse_id=world["warehouse"],
            consignee_id=world["consignee"],
            vendor_bill_no="GDJ/9501",
            bill_date=date.today(),
            declared_box_count=1,
        )
    )
    db.commit()
    db.close()

    steps = _steps(client, auth)["steps"]
    assert steps[0]["urgency"] == "now"
    assert steps[-1]["urgency"] == "soon"


def test_every_step_links_somewhere(client, world, auth):
    """A suggestion with nowhere to go is a complaint."""
    _make_freight(world, "COMPLETED", days_ago=10)
    _make_freight(world, "PLANNED", with_leg=True)

    for step in _steps(client, auth)["steps"]:
        assert step["to"].startswith("/")
        assert step["count"] > 0
        assert step["title"] and step["detail"]


def test_next_steps_needs_a_login(client, world):
    assert client.get("/api/next-steps").status_code == 401
