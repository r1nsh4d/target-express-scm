"""Where the lorry is.

The customer's tracking page has always been able to draw a vehicle and has
never had one to draw: the model existed, the page read it, and nothing in the
application ever wrote a point.

Two things these tests care about, and neither is the happy path:

  * A bad fix must not be stored. A phone occasionally reports the middle of
    the ocean, and one such point on a customer's map destroys the credibility
    of every other point on it.
  * Points are accepted only while the leg is running. A phone left on in a
    yard overnight would otherwise keep reporting, and a customer opening an
    old link would watch a lorry sitting somewhere it has no reason to be.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

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
)

# Kochi, roughly. A real point on a real route.
KOCHI = {"latitude": "10.0159", "longitude": "76.3419"}


@pytest.fixture()
def running(client):
    """A leg that has started and not closed, and the driver's token."""
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence, UserRole
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.user import User
    from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()
    user = User(
        full_name="Rajesh K",
        phone="9000000050",
        role=UserRole.DRIVER,
        hashed_password=hash_password("x"),
        is_active=True,
    )
    db.add(user)
    db.flush()

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

    owner = VehicleOwner(name="Target Express", phone="9000000051", is_active=True)
    db.add(owner)
    db.flush()
    vehicle = Vehicle(
        owner_id=owner.id, registration_no="KL07CW3317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Rajesh K", phone="9000000050", user_id=user.id, is_active=True)
    consignee = Consignee(
        name="Kannur Distribution Centre",
        type=ConsigneeType.DISTRIBUTION_CENTER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([vehicle, driver, consignee])
    db.flush()

    freight = Freight(
        trip_no="Y26008801",
        trip_date=date.today(),
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.IN_TRANSIT,
        point_count=1,
    )
    db.add(freight)
    db.flush()
    db.add(FreightPoint(freight_id=freight.id, sequence=1, consignee_id=consignee.id))
    leg = FreightLeg(
        freight_id=freight.id,
        sequence=1,
        vehicle_id=vehicle.id,
        driver_id=driver.id,
        start_odometer=1000,
        started_at=datetime.now() - timedelta(hours=2),
    )
    db.add(leg)
    db.commit()

    data = {
        "leg": str(leg.id),
        "freight": str(freight.id),
        "headers": {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"},
    }
    db.close()
    return data


def _send(client, running, pings):
    return client.post(
        f"/api/driver/legs/{running['leg']}/pings",
        json={"pings": pings},
        headers=running["headers"],
    )


def _stored(freight_id: str):
    from app.db.session import SessionLocal
    from app.models.tracking import VehiclePing
    from sqlalchemy import select

    db = SessionLocal()
    try:
        return list(
            db.execute(
                select(VehiclePing)
                .where(VehiclePing.freight_id == freight_id)
                .order_by(VehiclePing.recorded_at)
            ).scalars()
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def test_a_point_is_stored(client, running):
    assert _send(client, running, [KOCHI]).status_code == 204
    assert len(_stored(running["freight"])) == 1


def test_a_backlog_arrives_in_one_request(client, running):
    """The phone buffers while it has no signal. Fifty separate requests the
    moment a bar appears, on a connection that has just proved it is poor, is
    the wrong shape."""
    batch = [
        {
            "latitude": f"10.{100 + n}",
            "longitude": "76.3419",
            "recorded_at": (datetime.now() - timedelta(minutes=50 - n)).isoformat(),
        }
        for n in range(25)
    ]
    assert _send(client, running, batch).status_code == 204
    assert len(_stored(running["freight"])) == 25


def test_the_phones_own_timestamp_is_kept(client, running):
    """`recorded_at` is the truth; when it reached us is not. The points
    collected during a twenty-minute dead spot are the interesting ones."""
    when = (datetime.now() - timedelta(minutes=40)).replace(microsecond=0)
    _send(client, running, [{**KOCHI, "recorded_at": when.isoformat()}])

    stored = _stored(running["freight"])[0]
    assert abs((stored.recorded_at.replace(tzinfo=None) - when).total_seconds()) < 2


def test_accuracy_and_speed_come_through(client, running):
    _send(client, running, [{**KOCHI, "accuracy_m": 12, "speed_kmph": "54.5"}])
    stored = _stored(running["freight"])[0]
    assert stored.accuracy_m == 12
    assert float(stored.speed_kmph) == 54.5


# ---------------------------------------------------------------------------
# Bad fixes
# ---------------------------------------------------------------------------


def test_a_point_in_the_ocean_is_dropped(client, running):
    """One of these on a customer's map destroys the credibility of every other
    point on it."""
    res = _send(
        client,
        running,
        [KOCHI, {"latitude": "0.0", "longitude": "0.0"}],
    )
    assert res.status_code == 204
    assert len(_stored(running["freight"])) == 1, "a null-island fix was stored"


def test_a_point_on_another_continent_is_dropped(client, running):
    _send(client, running, [{"latitude": "51.5", "longitude": "-0.12"}])
    assert _stored(running["freight"]) == []


def test_a_bad_fix_does_not_lose_the_good_ones_beside_it(client, running):
    """A batch is not rejected wholesale for one bad point, or a dead spot's
    worth of real positions would be thrown away with it."""
    _send(
        client,
        running,
        [KOCHI, {"latitude": "0", "longitude": "0"}, {"latitude": "11.25", "longitude": "75.78"}],
    )
    assert len(_stored(running["freight"])) == 2


def test_a_clock_set_wrong_cannot_place_a_point_in_the_future(client, running):
    """It would sort above every genuine point and show as the lorry's current
    position for as long as the phone's clock stays wrong."""
    ahead = (datetime.now() + timedelta(days=3)).isoformat()
    _send(client, running, [{**KOCHI, "recorded_at": ahead}])

    stored = _stored(running["freight"])[0]
    assert stored.recorded_at.replace(tzinfo=None) <= datetime.now() + timedelta(seconds=5)


# ---------------------------------------------------------------------------
# When it is not running
# ---------------------------------------------------------------------------


def test_nothing_is_recorded_after_the_leg_closes(client, running):
    """A phone left on in a yard would otherwise keep reporting, and a customer
    opening an old link would watch a lorry sitting in a yard."""
    from app.db.session import SessionLocal
    from app.models.freight import FreightLeg

    db = SessionLocal()
    leg = db.get(FreightLeg, running["leg"])
    leg.ended_at = datetime.now()
    db.commit()
    db.close()

    res = _send(client, running, [KOCHI])
    assert res.status_code == 204, "the driver cannot act on this, so it is not an error"
    assert _stored(running["freight"]) == []


def test_another_drivers_leg_is_refused(client, running):
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.fleet import Driver
    from app.models.user import User

    db = SessionLocal()
    other = User(
        full_name="Someone Else",
        phone="9000000052",
        role=UserRole.DRIVER,
        hashed_password=hash_password("x"),
        is_active=True,
    )
    db.add(other)
    db.flush()
    db.add(Driver(name="Someone Else", phone="9000000052", user_id=other.id, is_active=True))
    db.commit()
    token = create_access_token(str(other.id), other.role)
    db.close()

    res = client.post(
        f"/api/driver/legs/{running['leg']}/pings",
        json={"pings": [KOCHI]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_pings_need_a_driver_login(client, running):
    res = client.post(f"/api/driver/legs/{running['leg']}/pings", json={"pings": [KOCHI]})
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# What the customer sees
# ---------------------------------------------------------------------------


def test_the_latest_point_reaches_the_tracking_page(client, running):
    """The whole reason this exists."""
    from app.db.session import SessionLocal
    from app.models.freight import FreightPoint
    from app.models.tracking import TrackingSession
    from sqlalchemy import select

    _send(
        client,
        running,
        [
            {**KOCHI, "recorded_at": (datetime.now() - timedelta(minutes=30)).isoformat()},
            {
                "latitude": "11.2588",
                "longitude": "75.7804",
                "recorded_at": datetime.now().isoformat(),
            },
        ],
    )

    db = SessionLocal()
    point = db.execute(
        select(FreightPoint).where(FreightPoint.freight_id == running["freight"])
    ).scalars().first()
    session = TrackingSession(
        freight_point_id=point.id,
        token="a-token-for-the-ping-test",
        expires_at=datetime.now() + timedelta(days=3),
    )
    db.add(session)
    db.commit()
    db.close()

    body = client.get("/api/track/a-token-for-the-ping-test").json()
    assert body["vehicle_position"] is not None, "the page had no vehicle to draw"
    assert round(body["vehicle_position"]["latitude"], 2) == 11.26, "not the most recent point"


# ---------------------------------------------------------------------------
# What the customer is actually told
# ---------------------------------------------------------------------------


@pytest.fixture()
def tracked(client, running):
    """A tracking link for the stop, with the stop's own pin dropped."""
    from app.db.session import SessionLocal
    from app.models.freight import FreightPoint
    from app.models.tracking import TrackingSession
    from sqlalchemy import select

    db = SessionLocal()
    point = db.execute(
        select(FreightPoint).where(FreightPoint.freight_id == running["freight"])
    ).scalars().first()
    # Kannur, which is about 220 km up the coast from Kochi.
    point.latitude = Decimal("11.8745")
    point.longitude = Decimal("75.3704")
    db.add(
        TrackingSession(
            freight_point_id=point.id,
            token="eta-test-token",
            expires_at=datetime.now() + timedelta(days=3),
        )
    )
    db.commit()
    db.close()
    return "eta-test-token"


def test_with_no_position_there_is_no_estimate(client, running, tracked):
    """Nothing invented before the lorry has reported."""
    body = client.get(f"/api/track/{tracked}").json()
    assert body["vehicle_position"] is None
    assert body["distance_km"] is None
    assert body["eta_minutes"] is None


def test_a_position_produces_a_distance_and_a_time(client, running, tracked):
    """The whole chain: the driver's phone reports, and the customer is told
    how far away it is and roughly how long."""
    # Kozhikode, roughly 90 km short of Kannur.
    _send(client, running, [{"latitude": "11.2588", "longitude": "75.7804"}])

    body = client.get(f"/api/track/{tracked}").json()
    assert body["vehicle_position"] is not None
    assert 60 < body["distance_km"] < 110, body["distance_km"]
    assert body["eta_minutes"] is not None
    # Around 90 km of straight line, so a couple of hours of road.
    assert 90 < body["eta_minutes"] < 320, body["eta_minutes"]


def test_closer_means_sooner(client, running, tracked):
    """Obvious, and worth a test: an estimate that does not fall as the lorry
    approaches is worse than none."""
    _send(client, running, [
        {"latitude": "11.2588", "longitude": "75.7804",
         "recorded_at": (datetime.now() - timedelta(hours=1)).isoformat()},
    ])
    far = client.get(f"/api/track/{tracked}").json()

    # Thalassery, about 20 km out.
    _send(client, running, [{"latitude": "11.7480", "longitude": "75.4929"}])
    near = client.get(f"/api/track/{tracked}").json()

    assert near["distance_km"] < far["distance_km"]
    assert near["eta_minutes"] < far["eta_minutes"]


def test_a_customer_with_no_pin_gets_no_estimate(client, running, tracked):
    """Measuring to the middle of their town and calling it an estimate is
    worse than saying nothing."""
    from app.db.session import SessionLocal
    from app.models.freight import FreightPoint
    from sqlalchemy import select

    db = SessionLocal()
    point = db.execute(
        select(FreightPoint).where(FreightPoint.freight_id == running["freight"])
    ).scalars().first()
    point.latitude = None
    point.longitude = None
    db.commit()
    db.close()

    _send(client, running, [{"latitude": "11.2588", "longitude": "75.7804"}])
    body = client.get(f"/api/track/{tracked}").json()

    assert body["vehicle_position"] is not None, "the map can still be drawn"
    assert body["eta_minutes"] is None, "but not an estimate"


def test_stops_ahead_push_the_estimate_out(client, running, tracked):
    """Two deliveries before yours is most of an hour, and the estimate has to
    say so or it is wrong every time."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, GeoConfidence
    from app.models.freight import FreightPoint
    from sqlalchemy import select

    _send(client, running, [{"latitude": "11.2588", "longitude": "75.7804"}])
    alone = client.get(f"/api/track/{tracked}").json()["eta_minutes"]

    db = SessionLocal()
    point = db.execute(
        select(FreightPoint).where(FreightPoint.freight_id == running["freight"])
    ).scalars().first()
    point.sequence = 3
    other = Consignee(
        name="Somewhere Else",
        type=ConsigneeType.RETAIL_CUSTOMER,
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add(other)
    db.flush()
    for seq in (1, 2):
        db.add(FreightPoint(freight_id=running["freight"], sequence=seq, consignee_id=other.id))
    db.commit()
    db.close()

    after = client.get(f"/api/track/{tracked}").json()
    assert after["stops_before"] == 2
    assert after["eta_minutes"] > alone, "the stops ahead were not counted"
