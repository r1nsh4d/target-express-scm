"""Correcting a rate card, which is not the same as changing a rate.

There was no edit at all, on the reasoning that a rate agreed in April must
still price an April freight in December. That reasoning is right about rate
CHANGES and wrong about typos: somebody enters Godrej OCP at 1,687 instead of
1,867, nothing has been billed on it, and the only way out was to retire the
card and re-key eleven fields. That is how a master list stops being trusted.

So the line is drawn at the invoice, not at the keystroke:

  * UNBILLED, EDITABLE. Nothing has gone to the vendor on this card, so
    correcting it changes nobody's copy of anything.
  * BILLED, FROZEN. Editing would reprice work the vendor already has a bill
    for, and the two copies would stop reconciling. Refused, with the reason
    and the way forward in the message rather than a bare 409.
  * A DISPATCHED FREIGHT IS SAFE EITHER WAY. It carries a frozen copy of the
    card's numbers in `rate_snapshot`, so a correction cannot move a price
    that has already been struck.
"""

from datetime import date, timedelta
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
    "rate_cards",
    "freights",
    "freight_points",
    "freight_legs",
    "trip_expenses",
    "vendor_invoices",
    "vendor_invoice_lines",
)

TODAY = date.today()
TRIP_DAY = TODAY - timedelta(days=5)


@pytest.fixture()
def scene(client, auth):
    """A division, a card with a transposed digit, and a completed freight."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.rating import RateCard
    from app.models.vendor import Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()

    vendor = Vendor(name="Godrej", payment_terms_days=30, is_active=True)
    db.add(vendor)
    db.flush()
    division = VendorDivision(
        vendor_id=vendor.id,
        name="Godrej OCP",
        code="GODREJ-OCP",
        invoice_series="191",
        gst_rate_percent=Decimal("12"),
        is_active=True,
    )
    warehouse = VendorWarehouse(vendor_id=vendor.id, name="Kochi godown", code="KOCHI")
    db.add_all([division, warehouse])
    db.flush()

    card = RateCard(
        vendor_division_id=division.id,
        # The typo: 1,687 where 1,867 was agreed.
        base_trip_amount=Decimal("1687"),
        included_km=60,
        included_points=3,
        extra_km_rate=Decimal("17"),
        extra_point_rate=Decimal("175"),
        effective_from=TRIP_DAY - timedelta(days=30),
        is_active=True,
    )
    db.add(card)
    db.flush()

    owner = VehicleOwner(name="Target Express", phone="9000000041", is_active=True)
    db.add(owner)
    db.flush()
    vehicle = Vehicle(
        owner_id=owner.id, registration_no="KL07CW3317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Suresh", phone="9000000032", is_active=True)
    consignee = Consignee(
        name="Kannur Distribution Centre",
        type=ConsigneeType.DISTRIBUTION_CENTER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([vehicle, driver, consignee])
    db.flush()

    freight = Freight(
        trip_no="Y26008001",
        trip_date=TRIP_DAY,
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.COMPLETED,
        point_count=1,
        total_km=100,
        rate_card_id=card.id,
    )
    db.add(freight)
    db.flush()
    db.add(FreightPoint(freight_id=freight.id, sequence=1, consignee_id=consignee.id))
    db.add(
        FreightLeg(
            freight_id=freight.id,
            sequence=1,
            vehicle_id=vehicle.id,
            driver_id=driver.id,
            start_odometer=1000,
            end_odometer=1100,
            leg_distance_km=100,
        )
    )
    db.commit()

    data = {
        "division": str(division.id),
        "card": str(card.id),
        "freight": str(freight.id),
    }
    db.close()
    return data


def _bill(client, auth, scene):
    return client.post(
        "/api/invoices",
        json={
            "vendor_division_id": scene["division"],
            "period_from": (TRIP_DAY - timedelta(days=1)).isoformat(),
            "period_to": TODAY.isoformat(),
        },
        headers=auth,
    )


# ---------------------------------------------------------------------------
# Before anything is billed
# ---------------------------------------------------------------------------


def test_a_card_that_has_billed_nothing_can_be_corrected(client, scene, auth):
    res = client.patch(
        f"/api/rate-cards/{scene['card']}",
        json={"base_trip_amount": "1867"},
        headers=auth,
    )
    assert res.status_code == 200, res.text

    cards = client.get("/api/rate-cards", headers=auth).json()
    assert Decimal(cards[0]["base_trip_amount"]) == Decimal("1867")


def test_the_screen_can_ask_whether_a_card_is_still_editable(client, scene, auth):
    """So somebody is told before filling in a form, not after."""
    res = client.get(f"/api/rate-cards/{scene['card']}/usage", headers=auth)
    assert res.status_code == 200, res.text

    usage = res.json()
    assert usage["editable"] is True
    assert usage["invoiced_freights"] == 0
    # It has priced a freight — just not an invoiced one.
    assert usage["freights"] == 1


def test_a_partial_edit_leaves_the_other_figures_alone(client, scene, auth):
    """A PATCH that omits the point rate must not blank it."""
    client.patch(
        f"/api/rate-cards/{scene['card']}",
        json={"base_trip_amount": "1867"},
        headers=auth,
    )
    card = client.get("/api/rate-cards", headers=auth).json()[0]
    assert Decimal(card["extra_point_rate"]) == Decimal("175")
    assert card["included_km"] == 60


# ---------------------------------------------------------------------------
# Once the vendor has the bill
# ---------------------------------------------------------------------------


def test_a_card_that_has_priced_an_invoice_is_frozen(client, scene, auth):
    assert _bill(client, auth, scene).status_code == 201

    res = client.patch(
        f"/api/rate-cards/{scene['card']}",
        json={"base_trip_amount": "1867"},
        headers=auth,
    )
    assert res.status_code == 409


def test_the_refusal_says_what_to_do_instead(client, scene, auth):
    """A bare 409 teaches nobody the supersede rule."""
    _bill(client, auth, scene)

    detail = client.patch(
        f"/api/rate-cards/{scene['card']}",
        json={"base_trip_amount": "1867"},
        headers=auth,
    ).json()["detail"]

    assert "new card" in detail.lower()
    assert "1 invoiced freight" in detail


def test_the_usage_check_flips_once_billed(client, scene, auth):
    _bill(client, auth, scene)

    usage = client.get(f"/api/rate-cards/{scene['card']}/usage", headers=auth).json()
    assert usage["editable"] is False
    assert usage["invoiced_freights"] == 1


def test_a_frozen_card_keeps_its_figures_after_a_refused_edit(client, scene, auth):
    """The refusal must not have half-applied."""
    _bill(client, auth, scene)
    client.patch(
        f"/api/rate-cards/{scene['card']}",
        json={"base_trip_amount": "9999", "extra_km_rate": "99"},
        headers=auth,
    )

    card = client.get("/api/rate-cards", headers=auth).json()[0]
    assert Decimal(card["base_trip_amount"]) == Decimal("1687")
    assert Decimal(card["extra_km_rate"]) == Decimal("17")


def test_superseding_still_works_when_a_card_is_frozen(client, scene, auth):
    """The way forward the refusal points at has to actually be open."""
    _bill(client, auth, scene)

    res = client.post(
        "/api/rate-cards",
        json={
            "vendor_division_id": scene["division"],
            "base_trip_amount": "1867",
            "included_km": 60,
            "included_points": 3,
            "extra_km_rate": "17",
            "extra_point_rate": "175",
            "effective_from": TODAY.isoformat(),
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text

    cards = client.get("/api/rate-cards", headers=auth).json()
    assert len(cards) == 2
