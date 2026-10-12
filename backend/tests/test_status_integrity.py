"""A freight's status moves forward, or it is cancelled.

Backwards used to be allowed. It should not have been: a dispatched trip has an
LR number out of a vehicle's book and tracking links in customers' hands, and a
completed one has odometer readings and payouts behind it. Dragging either back
to PLANNED leaves all of that pointing at a trip the system now says has not
happened, and nothing in the record admits it ever did.

So the rule is forward only, and the escape hatch is CANCELLED. A trip entered
wrongly is cancelled and entered again — the wrong one stays visible, with the
reason somebody typed, instead of being quietly rewritten into the right one.
That is the difference between a record and a draft.
"""

from datetime import date

import pytest

pytestmark = pytest.mark.tables(
    "users",
    "goods_categories",
    "vendors",
    "vendor_divisions",
    "vendor_warehouses",
    "consignees",
    "freights",
    "freight_points",
    "freight_legs",
    "consignments",
    "boxes",
    "tracking_sessions",
    "vehicle_pings",
    "audit_logs",
)


@pytest.fixture()
def freight(client, auth):
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence
    from app.models.freight import Freight, FreightPoint
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
    consignee = Consignee(
        name="Kannur Distribution Centre",
        type=ConsigneeType.DISTRIBUTION_CENTER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add(consignee)
    db.flush()

    f = Freight(
        trip_no="Y26009901",
        trip_date=date.today(),
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.PLANNED,
        point_count=1,
    )
    db.add(f)
    db.flush()
    db.add(FreightPoint(freight_id=f.id, sequence=1, consignee_id=consignee.id))
    db.commit()
    out = str(f.id)
    db.close()
    return out


def _set(client, auth, freight, status, reason="Corrected from the paper sheet"):
    return client.post(
        f"/api/freights/{freight}/status",
        json={"status": status, "reason": reason},
        headers=auth,
    )


def _status(client, auth, freight):
    return client.get(f"/api/freights/{freight}", headers=auth).json()["status"]


# ---------------------------------------------------------------------------
# Forward
# ---------------------------------------------------------------------------


def test_a_step_forward_is_allowed(client, freight, auth):
    assert _set(client, auth, freight, "LOADING").status_code == 200
    assert _status(client, auth, freight) == "LOADING"


def test_several_steps_forward_at_once_are_allowed(client, freight, auth):
    """A run finished on paper over two days and caught up afterwards."""
    assert _set(client, auth, freight, "COMPLETED").status_code == 200


def test_setting_the_same_status_is_harmless(client, freight, auth):
    assert _set(client, auth, freight, "PLANNED").status_code == 200


# ---------------------------------------------------------------------------
# Backwards
# ---------------------------------------------------------------------------


def test_a_step_backwards_is_refused(client, freight, auth):
    _set(client, auth, freight, "DISPATCHED")

    res = _set(client, auth, freight, "PLANNED")
    assert res.status_code == 409
    assert "only move forward" in res.json()["detail"]


def test_a_refused_move_leaves_the_status_alone(client, freight, auth):
    _set(client, auth, freight, "DISPATCHED")
    _set(client, auth, freight, "DRAFT")
    assert _status(client, auth, freight) == "DISPATCHED"


def test_the_message_says_what_to_do_instead(client, freight, auth):
    """The person reading this has a trip in the wrong state and needs to know
    the way out, not just that the door is shut."""
    _set(client, auth, freight, "COMPLETED")
    detail = _set(client, auth, freight, "IN_TRANSIT").json()["detail"]
    assert "cancel it and create a new one" in detail


# ---------------------------------------------------------------------------
# Cancelling, which is the way out
# ---------------------------------------------------------------------------


def test_a_trip_can_be_cancelled_from_anywhere(client, freight, auth):
    _set(client, auth, freight, "IN_TRANSIT")
    assert _set(client, auth, freight, "CANCELLED", "Vendor pulled the load").status_code == 200


def test_a_cancelled_trip_is_not_restarted(client, freight, auth):
    """It stays on the record with its reason. The replacement is a new trip."""
    _set(client, auth, freight, "CANCELLED", "Entered against the wrong vendor")

    res = _set(client, auth, freight, "PLANNED")
    assert res.status_code == 409
    assert "create a new one" in res.json()["detail"]


def test_cancelling_still_needs_a_reason(client, freight, auth):
    res = client.post(
        f"/api/freights/{freight}/status",
        json={"status": "CANCELLED"},
        headers=auth,
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# What is never set by hand
# ---------------------------------------------------------------------------


def test_billed_cannot_be_set_by_hand(client, freight, auth):
    """It follows from an invoice existing, so a billed freight always has a
    document behind it."""
    _set(client, auth, freight, "COMPLETED")
    res = _set(client, auth, freight, "BILLED")
    assert res.status_code == 400
    assert "issuing an" in res.json()["detail"]


def test_settled_cannot_be_set_by_hand(client, freight, auth):
    _set(client, auth, freight, "COMPLETED")
    assert _set(client, auth, freight, "SETTLED").status_code == 400


# ---------------------------------------------------------------------------
# Editing, which stops at dispatch
# ---------------------------------------------------------------------------


def test_a_freight_can_be_edited_before_dispatch(client, freight, auth):
    res = client.patch(
        f"/api/freights/{freight}",
        json={"remarks": "Load the fragile ones last"},
        headers=auth,
    )
    assert res.status_code == 200, res.text


def test_a_dispatched_freight_cannot_be_edited(client, freight, auth):
    """The LR number is out of the vehicle's book and the customers have
    tracking links. The trip is a record now, not a plan."""
    _set(client, auth, freight, "DISPATCHED")

    res = client.patch(
        f"/api/freights/{freight}",
        json={"trip_date": date.today().isoformat()},
        headers=auth,
    )
    assert res.status_code == 409
    assert "not been dispatched" in res.json()["detail"]
