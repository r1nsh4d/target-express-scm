"""The customer rating the delivery from their own tracking link.

This is the only account of a delivery that does not come from the people who
made it. A driver who is quick and careful and one who leaves cartons in the
rain look identical in a box count.

The rules worth holding: you cannot rate a delivery that has not happened, a
remark without a score is still worth keeping, and a tap on the wrong star can
be put right.
"""

from datetime import date, datetime, timedelta

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
    "tracking_sessions",
    "vehicle_pings",
    "point_unloading_items",
)


@pytest.fixture()
def delivered(client):
    """A stop that has been delivered, with a live tracking link."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import (
        ConsigneeType,
        FreightPointStatus,
        FreightStatus,
        GeoConfidence,
    )
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.tracking import TrackingSession
    from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()
    category = GoodsCategory(name="Furniture", code="FURNITURE")
    vendor = Vendor(name="Godrej", payment_terms_days=30, is_active=True)
    db.add_all([category, vendor])
    db.flush()
    division = VendorDivision(
        vendor_id=vendor.id,
        goods_category_id=category.id,
        name="Godrej Interio",
        code="GODREJ-INTERIO",
        invoice_series="191",
        is_active=True,
    )
    warehouse = VendorWarehouse(vendor_id=vendor.id, name="Kochi godown", code="KOCHI")
    db.add_all([division, warehouse])
    db.flush()
    owner = VehicleOwner(name="Target Express", phone="9000000070", is_active=True)
    db.add(owner)
    db.flush()
    vehicle = Vehicle(
        owner_id=owner.id, registration_no="KL07CW3317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Rajesh K", phone="9000000071", is_active=True)
    consignee = Consignee(
        name="Anand Agencies",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([vehicle, driver, consignee])
    db.flush()

    freight = Freight(
        trip_no="Y26009701",
        trip_date=date.today(),
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.IN_TRANSIT,
        point_count=1,
    )
    db.add(freight)
    db.flush()
    point = FreightPoint(
        freight_id=freight.id,
        sequence=1,
        consignee_id=consignee.id,
        loaded_box_count=4,
        delivered_box_count=4,
        status=FreightPointStatus.DELIVERED,
    )
    db.add(point)
    db.add(
        FreightLeg(
            freight_id=freight.id,
            sequence=1,
            vehicle_id=vehicle.id,
            driver_id=driver.id,
            start_odometer=1000,
        )
    )
    db.flush()
    db.add(
        TrackingSession(
            freight_point_id=point.id,
            token="rate-me-token",
            expires_at=datetime.now() + timedelta(days=3),
        )
    )
    db.commit()
    data = {"token": "rate-me-token", "point": str(point.id)}
    db.close()
    return data


def _rate(client, token, **body):
    return client.post(f"/api/track/{token}/rating", json=body)


# ---------------------------------------------------------------------------
# Leaving one
# ---------------------------------------------------------------------------


def test_a_rating_is_kept(client, delivered):
    res = _rate(client, delivered["token"], rating=5)
    assert res.status_code == 200, res.text
    assert res.json()["rating"] == 5


def test_a_remark_without_a_score_is_still_worth_keeping(client, delivered):
    """"They carried it up without being asked" is actionable in a way a 5 is
    not. Refusing it because no star was tapped loses the useful half."""
    res = _rate(client, delivered["token"], remarks="Carried it up without being asked")
    assert res.status_code == 200, res.text
    assert res.json()["rating"] is None
    assert "without being asked" in res.json()["remarks"]


def test_neither_a_score_nor_a_remark_is_refused(client, delivered):
    assert _rate(client, delivered["token"]).status_code == 422


def test_a_mistaken_tap_can_be_corrected(client, delivered):
    """A rating nobody can change is a rating nobody trusts."""
    _rate(client, delivered["token"], rating=1)
    res = _rate(client, delivered["token"], rating=4, remarks="Sorry, wrong button")
    assert res.json()["rating"] == 4


def test_the_rating_comes_back_on_the_page(client, delivered):
    """So it shows what they said rather than asking twice."""
    _rate(client, delivered["token"], rating=4, remarks="On time")
    body = client.get(f"/api/track/{delivered['token']}").json()
    assert body["customer_rating"] == 4
    assert body["customer_remarks"] == "On time"


@pytest.mark.parametrize("score", [0, 6, -1, 99])
def test_a_score_outside_one_to_five_is_refused(client, delivered, score):
    assert _rate(client, delivered["token"], rating=score).status_code == 422


# ---------------------------------------------------------------------------
# When it may not be left
# ---------------------------------------------------------------------------


def test_an_undelivered_stop_cannot_be_rated(client, delivered):
    """Rating a delivery that has not happened is either a mistake or somebody
    rating the wait, and neither is what this measures."""
    from app.db.session import SessionLocal
    from app.models.enums import FreightPointStatus
    from app.models.freight import FreightPoint

    db = SessionLocal()
    db.get(FreightPoint, delivered["point"]).status = FreightPointStatus.ARRIVED
    db.commit()
    db.close()

    res = _rate(client, delivered["token"], rating=5)
    assert res.status_code == 409
    assert "handed over" in res.json()["detail"]


def test_an_expired_link_cannot_rate(client, delivered):
    """It is not a separate door."""
    from app.db.session import SessionLocal
    from app.models.tracking import TrackingSession
    from sqlalchemy import select

    db = SessionLocal()
    session = db.execute(
        select(TrackingSession).where(TrackingSession.token == delivered["token"])
    ).scalar_one()
    session.expires_at = datetime.now() - timedelta(hours=1)
    db.commit()
    db.close()

    assert _rate(client, delivered["token"], rating=5).status_code == 404


def test_an_unknown_token_cannot_rate(client, delivered):
    assert _rate(client, "not-a-real-token", rating=5).status_code == 404
