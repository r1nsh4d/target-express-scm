"""The customer's tracking link, and what happens when it runs out.

A link lives three days from dispatch. That is the privacy decision — the page
shows a customer's address, their delivery and the vehicle's position, so it
should not stay open on the internet forever.

What was wrong was not the expiry. It was that the office screen went on
offering the link for days after it stopped working: the customer opened it,
read "contact the sender for a new link", rang the office, and the office was
looking at a link that appeared perfectly fine and had no way to issue another.

So: a link is shown only while it works, an expired one says so, and a fresh
one can be issued.
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
)


@pytest.fixture()
def dispatched(client, auth):
    """One dispatched freight with a live tracking link on its only stop."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.tracking import TrackingSession
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

    owner = VehicleOwner(name="Target Express", phone="9000000042", is_active=True)
    db.add(owner)
    db.flush()
    vehicle = Vehicle(
        owner_id=owner.id, registration_no="KL07CW3317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Rajesh K", phone="9000000033", is_active=True)
    consignee = Consignee(
        name="Anand Agencies",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Kannur",
        phone="9000012345",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([vehicle, driver, consignee])
    db.flush()

    freight = Freight(
        trip_no="Y26007001",
        trip_date=date.today(),
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.DISPATCHED,
        point_count=1,
        lr_no="901",
    )
    db.add(freight)
    db.flush()
    point = FreightPoint(freight_id=freight.id, sequence=1, consignee_id=consignee.id)
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

    session = TrackingSession(
        freight_point_id=point.id,
        token="a-live-token-for-the-test",
        expires_at=datetime.now() + timedelta(days=3),
        sent_to_phone=consignee.phone,
    )
    db.add(session)
    db.commit()

    data = {"freight": str(freight.id), "point": str(point.id), "token": session.token}
    db.close()
    return data


def _expire(token: str) -> None:
    """Age the link past its three days, as the calendar would."""
    from app.db.session import SessionLocal
    from app.models.tracking import TrackingSession
    from sqlalchemy import select

    db = SessionLocal()
    session = db.execute(
        select(TrackingSession).where(TrackingSession.token == token)
    ).scalar_one()
    session.expires_at = datetime.now() - timedelta(hours=1)
    db.commit()
    db.close()


def _point(client, auth, dispatched):
    freight = client.get(f"/api/freights/{dispatched['freight']}", headers=auth).json()
    return freight["points"][0]


# ---------------------------------------------------------------------------
# While it works
# ---------------------------------------------------------------------------


def test_a_live_link_is_offered_and_opens(client, dispatched, auth):
    point = _point(client, auth, dispatched)
    assert point["tracking_url"], "no link offered for a dispatched stop"
    assert point["tracking_expired"] is False

    assert client.get(f"/api/track/{dispatched['token']}").status_code == 200


# ---------------------------------------------------------------------------
# Once it has run out
# ---------------------------------------------------------------------------


def test_an_expired_link_is_not_offered(client, dispatched, auth):
    """The bug. The office was handing out a link the customer could not open,
    and nothing on screen said so."""
    _expire(dispatched["token"])

    point = _point(client, auth, dispatched)
    assert point["tracking_url"] is None


def test_an_expired_link_says_it_expired(client, dispatched, auth):
    """Not the same as never having had one — the screen offers to reissue."""
    _expire(dispatched["token"])
    assert _point(client, auth, dispatched)["tracking_expired"] is True


def test_the_customer_is_turned_away(client, dispatched, auth):
    _expire(dispatched["token"])
    res = client.get(f"/api/track/{dispatched['token']}")
    assert res.status_code == 404
    assert "no longer active" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Issuing a new one
# ---------------------------------------------------------------------------


def test_a_fresh_link_can_be_issued(client, dispatched, auth):
    """What the expired page tells the customer to ask for, and what the office
    previously had no way to produce."""
    _expire(dispatched["token"])

    res = client.post(
        f"/api/freights/{dispatched['freight']}/points/{dispatched['point']}/tracking-link",
        headers=auth,
    )
    assert res.status_code == 200, res.text

    point = res.json()["points"][0]
    assert point["tracking_url"], "reissue produced no link"
    assert point["tracking_expired"] is False


def test_the_new_link_actually_opens(client, dispatched, auth):
    _expire(dispatched["token"])
    res = client.post(
        f"/api/freights/{dispatched['freight']}/points/{dispatched['point']}/tracking-link",
        headers=auth,
    )
    token = res.json()["points"][0]["tracking_url"].rsplit("/", 1)[-1]
    assert client.get(f"/api/track/{token}").status_code == 200


def test_the_old_link_is_retired(client, dispatched, auth):
    """Two live links to one delivery is one more than anybody can keep track
    of, and an expiry that can be bypassed by an old link is not an expiry."""
    client.post(
        f"/api/freights/{dispatched['freight']}/points/{dispatched['point']}/tracking-link",
        headers=auth,
    )
    assert client.get(f"/api/track/{dispatched['token']}").status_code == 404


def test_reissuing_before_dispatch_is_refused(client, dispatched, auth):
    """There is nothing to follow until the vehicle leaves."""
    from app.db.session import SessionLocal
    from app.models.enums import FreightStatus
    from app.models.freight import Freight

    db = SessionLocal()
    db.get(Freight, dispatched["freight"]).status = FreightStatus.PLANNED
    db.commit()
    db.close()

    res = client.post(
        f"/api/freights/{dispatched['freight']}/points/{dispatched['point']}/tracking-link",
        headers=auth,
    )
    assert res.status_code == 409
    assert "dispatched" in res.json()["detail"]


def test_a_stop_on_another_freight_is_refused(client, dispatched, auth):
    res = client.post(
        f"/api/freights/{dispatched['freight']}/points/"
        "00000000-0000-0000-0000-000000000000/tracking-link",
        headers=auth,
    )
    assert res.status_code == 404


def test_reissuing_needs_a_login(client, dispatched):
    res = client.post(
        f"/api/freights/{dispatched['freight']}/points/{dispatched['point']}/tracking-link"
    )
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# What Postgres actually returns
# ---------------------------------------------------------------------------


def test_the_freight_detail_survives_a_timezone_aware_expiry(client, dispatched, auth):
    """The bug this guards against listed a freight perfectly and then said
    "Trip not found" when you opened it.

    Postgres stores these columns as timestamptz and psycopg returns them
    timezone-AWARE. `datetime.now()` is naive, and Python raises TypeError
    rather than comparing them — a 500 on the detail page. SQLite has no
    timestamptz and returns naive, so the whole suite passed while the live
    system was broken.

    So the aware value is forced in here rather than waited for.
    """
    from datetime import timezone as _tz

    from app.db.session import SessionLocal
    from app.models.tracking import TrackingSession
    from sqlalchemy import select

    db = SessionLocal()
    session = db.execute(
        select(TrackingSession).where(TrackingSession.token == dispatched["token"])
    ).scalar_one()
    # Exactly what psycopg hands back for a timestamptz column.
    session.expires_at = datetime.now(_tz.utc) + timedelta(days=3)
    db.commit()
    db.close()

    res = client.get(f"/api/freights/{dispatched['freight']}", headers=auth)
    assert res.status_code == 200, (
        "the freight detail failed on a timezone-aware expiry — this is the "
        f"bug that showed as 'Trip not found': {res.text[:300]}"
    )
    assert res.json()["points"][0]["tracking_url"], "a live link was not offered"


def test_the_customer_page_survives_a_timezone_aware_expiry(client, dispatched, auth):
    """Same fault, older, and worse: it would have refused every valid link."""
    from datetime import timezone as _tz

    from app.db.session import SessionLocal
    from app.models.tracking import TrackingSession
    from sqlalchemy import select

    db = SessionLocal()
    session = db.execute(
        select(TrackingSession).where(TrackingSession.token == dispatched["token"])
    ).scalar_one()
    session.expires_at = datetime.now(_tz.utc) + timedelta(days=3)
    db.commit()
    db.close()

    res = client.get(f"/api/track/{dispatched['token']}")
    assert res.status_code == 200, f"a live link was refused: {res.text[:300]}"


def test_an_aware_expiry_in_the_past_is_still_refused(client, dispatched, auth):
    """The fix must not make everything valid."""
    from datetime import timezone as _tz

    from app.db.session import SessionLocal
    from app.models.tracking import TrackingSession
    from sqlalchemy import select

    db = SessionLocal()
    session = db.execute(
        select(TrackingSession).where(TrackingSession.token == dispatched["token"])
    ).scalar_one()
    session.expires_at = datetime.now(_tz.utc) - timedelta(hours=1)
    db.commit()
    db.close()

    assert client.get(f"/api/track/{dispatched['token']}").status_code == 404

    point = client.get(f"/api/freights/{dispatched['freight']}", headers=auth).json()["points"][0]
    assert point["tracking_url"] is None
    assert point["tracking_expired"] is True


# ---------------------------------------------------------------------------
# The consignment note
# ---------------------------------------------------------------------------


def test_the_note_carries_what_an_lr_needs(client, dispatched, auth):
    """The LR travels with the goods and the consignee is entitled to their
    part of it: which lorry, from where, under which number."""
    body = client.get(f"/api/track/{dispatched['token']}").json()

    assert body["lr_no"] == "901"
    assert body["trip_no"] == "Y26007001"
    assert body["trip_date"]
    assert body["vendor_name"] == "Godrej"
    assert body["from_warehouse"] == "Kochi godown"
    assert body["vehicle_no"] == "KL07CW3317"
    assert body["driver_name"] == "Rajesh K"
    assert body["consignee_name"] == "Anand Agencies"


def test_the_note_says_nothing_about_the_rest_of_the_run(client, dispatched, auth):
    """A consignee's copy that leaked the other stops would be worse than no
    copy at all — it tells one customer where a competitor's goods are going
    and what the lorry is carrying for them."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, GeoConfidence
    from app.models.freight import FreightPoint

    db = SessionLocal()
    rival = Consignee(
        name="Somebody Elses Shop",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Kozhikode",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add(rival)
    db.flush()
    db.add(FreightPoint(freight_id=dispatched["freight"], sequence=2, consignee_id=rival.id))
    db.commit()
    db.close()

    raw = client.get(f"/api/track/{dispatched['token']}").text
    assert "Somebody Elses Shop" not in raw
    assert "Kozhikode" not in raw


def test_the_note_is_refused_with_the_link(client, dispatched, auth):
    """It is not a separate door. An expired link takes the note with it."""
    _expire(dispatched["token"])
    assert client.get(f"/api/track/{dispatched['token']}").status_code == 404
