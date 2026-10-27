"""A Dost and a 403 are different money for the same run.

The base trip charge is not one number per vendor. It is one number per
vendor division PER VEHICLE TYPE: Godrej pays one base for a Dost, another
for a 403, another for an Ace, and the kilometres and points on top are
priced from that same card.

The selection rule itself is covered in `test_rate_card_selection.py` on
plain objects. What is covered here is everything around it, which is where
this actually breaks in use:

  * A card can be created against a vehicle type through the API, and comes
    back naming it. A screen that shows two cards with the same figures and
    no vehicle against either makes a deliberate pair read as a duplicate.
  * The type is read off the LORRY ASSIGNED TO THE TRIP, so the same run
    prices differently depending on which one went.
  * And the gap: a division priced per type with no catch-all card cannot
    price a lorry whose type was never set. The arithmetic is fine and there
    is simply no card, which is a configuration gap discovered at invoice
    time unless somebody is told earlier.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.tables(
    "users",
    "roles",
    "role_capabilities",
    "role_screens",
    "goods_categories",
    "vendors",
    "vendor_divisions",
    "vendor_warehouses",
    "vehicle_types",
    "vehicle_owners",
    "vehicles",
    "drivers",
    "rate_cards",
)

APRIL = date(2026, 4, 1)
TRIP_DAY = date.today() - timedelta(days=3)


@pytest.fixture()
def scene(client, auth):
    """One division, two kinds of lorry, and a lorry of each on the yard."""
    from app.db.session import SessionLocal
    from app.models.enums import VehicleOwnership
    from app.models.fleet import Vehicle, VehicleType
    from app.models.vendor import GoodsCategory, Vendor, VendorDivision

    db = SessionLocal()
    try:
        category = GoodsCategory(code="FURN", name="Furniture")
        db.add(category)
        db.flush()

        vendor = Vendor(name="Godrej", gstin="32AAACG0000A1Z5")
        db.add(vendor)
        db.flush()

        division = VendorDivision(
            vendor_id=vendor.id,
            name="Godrej OCP",
            code="GODREJ-OCP",
            goods_category_id=category.id,
            gst_rate_percent=Decimal("12.00"),
        )
        db.add(division)

        dost = VehicleType(name="Dost", capacity_kg=1_250)
        four_oh_three = VehicleType(name="403", capacity_kg=2_000)
        db.add_all([dost, four_oh_three])
        db.flush()

        small = Vehicle(
            registration_no="KL07CW3317",
            vehicle_type_id=dost.id,
            ownership=VehicleOwnership.OWNED,
            lr_next_number=1,
        )
        big = Vehicle(
            registration_no="KL07DE1129",
            vehicle_type_id=four_oh_three.id,
            ownership=VehicleOwnership.OWNED,
            lr_next_number=1,
        )
        # A lorry nobody set a type on, which is the ordinary state of a
        # vehicle added in a hurry at the counter.
        untyped = Vehicle(
            registration_no="KL10AL4477",
            ownership=VehicleOwnership.OWNED,
            lr_next_number=1,
        )
        db.add_all([small, big, untyped])
        db.commit()

        return {
            "division": str(division.id),
            "dost": str(dost.id),
            "403": str(four_oh_three.id),
            "small": str(small.id),
            "big": str(big.id),
            "untyped": str(untyped.id),
        }
    finally:
        db.close()


def _card(client, auth, division, *, base, vehicle_type_id=None):
    return client.post(
        "/api/rate-cards",
        json={
            "vendor_division_id": division,
            "vehicle_type_id": vehicle_type_id,
            "effective_from": APRIL.isoformat(),
            "base_trip_amount": str(base),
            "included_km": 60,
            "extra_km_rate": "17.00",
            "included_points": 3,
            "extra_point_rate": "175.00",
        },
        headers=auth,
    )


# ---------------------------------------------------------------------------
# A card knows which lorry it prices
# ---------------------------------------------------------------------------


def test_a_card_can_name_a_vehicle_type(client, scene, auth):
    res = _card(client, auth, scene["division"], base="1867.00", vehicle_type_id=scene["dost"])
    assert res.status_code == 201, res.text

    out = res.json()
    assert out["vehicle_type_id"] == scene["dost"]
    assert out["vehicle_type_name"] == "Dost"


def test_a_card_naming_no_type_is_the_catch_all(client, scene, auth):
    out = _card(client, auth, scene["division"], base="1867.00").json()

    assert out["vehicle_type_id"] is None
    assert out["vehicle_type_name"] is None


def test_the_list_names_the_vehicle_on_every_card(client, scene, auth):
    """Two cards with the same figures and no vehicle against either read as
    a duplicate rather than as a deliberate pair."""
    _card(client, auth, scene["division"], base="1867.00", vehicle_type_id=scene["dost"])
    _card(client, auth, scene["division"], base="2450.00", vehicle_type_id=scene["403"])

    rows = client.get(
        "/api/rate-cards", params={"vendor_division_id": scene["division"]}, headers=auth
    ).json()

    assert {r["vehicle_type_name"] for r in rows} == {"Dost", "403"}


def test_a_vehicle_type_that_does_not_exist_is_refused(client, scene, auth):
    """A card pointing at nothing prices nothing and says nothing about why."""
    import uuid

    res = _card(
        client, auth, scene["division"], base="1867.00", vehicle_type_id=str(uuid.uuid4())
    )
    assert res.status_code == 404


def test_two_cards_for_two_types_on_one_division_are_both_kept(client, scene, auth):
    """The uniqueness rule is division + type + date, so this is the normal
    arrangement and not a clash."""
    first = _card(
        client, auth, scene["division"], base="1867.00", vehicle_type_id=scene["dost"]
    )
    second = _card(
        client, auth, scene["division"], base="2450.00", vehicle_type_id=scene["403"]
    )

    assert first.status_code == 201
    assert second.status_code == 201, second.text


# ---------------------------------------------------------------------------
# Which card prices the trip
# ---------------------------------------------------------------------------


def _resolve(division, vehicle_id):
    """The card a trip on this lorry would be priced on."""
    from app.db.session import SessionLocal
    from app.models.fleet import Vehicle
    from app.services.rating import resolve_rate_card

    db = SessionLocal()
    try:
        vehicle = db.get(Vehicle, vehicle_id)
        return resolve_rate_card(db, division, TRIP_DAY, vehicle.vehicle_type_id)
    finally:
        db.close()


def test_the_lorry_sent_decides_the_base_charge(client, scene, auth):
    """The same run, the same vendor, two different prices."""
    _card(client, auth, scene["division"], base="1867.00", vehicle_type_id=scene["dost"])
    _card(client, auth, scene["division"], base="2450.00", vehicle_type_id=scene["403"])

    assert _resolve(scene["division"], scene["small"]).base_trip_amount == Decimal("1867.00")
    assert _resolve(scene["division"], scene["big"]).base_trip_amount == Decimal("2450.00")


def test_a_type_with_no_card_of_its_own_falls_back(client, scene, auth):
    """The catch-all is what makes adding a third kind of lorry safe: it
    prices on the general card until somebody agrees a rate for it."""
    _card(client, auth, scene["division"], base="1867.00")
    _card(client, auth, scene["division"], base="2450.00", vehicle_type_id=scene["403"])

    assert _resolve(scene["division"], scene["small"]).base_trip_amount == Decimal("1867.00")
    assert _resolve(scene["division"], scene["big"]).base_trip_amount == Decimal("2450.00")


def test_a_lorry_with_no_type_set_uses_the_catch_all(client, scene, auth):
    _card(client, auth, scene["division"], base="1867.00")
    _card(client, auth, scene["division"], base="2450.00", vehicle_type_id=scene["403"])

    assert _resolve(scene["division"], scene["untyped"]).base_trip_amount == Decimal("1867.00")


def test_priced_per_type_with_no_catch_all_cannot_price_an_untyped_lorry(
    client, scene, auth
):
    """The gap worth knowing about.

    Nothing is wrong with the arithmetic; there is simply no card for that
    lorry, and the freight cannot be priced or invoiced. It surfaces at the
    end of the month unless the rate card screen says so first, which is why
    it does.
    """
    from app.services.rating import RateCardNotFound

    _card(client, auth, scene["division"], base="1867.00", vehicle_type_id=scene["dost"])
    _card(client, auth, scene["division"], base="2450.00", vehicle_type_id=scene["403"])

    with pytest.raises(RateCardNotFound) as refused:
        _resolve(scene["division"], scene["untyped"])

    # Named, because the message reaches an operator on the trip screen.
    assert "Godrej OCP" in str(refused.value)
