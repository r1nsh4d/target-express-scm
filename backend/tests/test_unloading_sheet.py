"""The driver logging what he actually carried in.

The vendor's unloading charge was worked out from the boxes on the bill, which
is a guess at what happened. The bill says five chairs; four came off the lorry
and one was refused at the door, and the sheet charged for five anyway. The man
who carried them knows, and he has a phone in his hand.

So the thing these tests care about is that his log WINS. Everything else here
is in service of that: the charge and his pay come off the same rate row, the
climb he reports is the one that is priced, and an invoice raised afterwards
reads what he logged rather than what the paperwork assumed.
"""

from datetime import date
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
    "unloading_item_rates",
    "freights",
    "freight_points",
    "freight_legs",
    "consignments",
    "boxes",
    "point_unloading_items",
    "trip_expenses",
)


@pytest.fixture()
def door(client):
    """A furniture stop on the second floor, five chairs on the bill."""
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.consignment import Box, Consignment
    from app.models.enums import (
        BoxStatus,
        ConsigneeType,
        FreightStatus,
        GeoConfidence,
        UnloadingBasis,
        UserRole,
    )
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.rating import UnloadingItemRate
    from app.models.user import User
    from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()
    user = User(
        full_name="Rajesh K",
        phone="9000000060",
        role=UserRole.DRIVER,
        hashed_password=hash_password("x"),
        is_active=True,
        can_view_earnings=True,
    )
    db.add(user)
    db.flush()

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

    for code, name, base, floor_rate, d_base, d_floor in (
        ("CHAIR", "Chair", "50", "10", "30", "6"),
        ("WARDROBE", "Wardrobe", "400", "80", "240", "48"),
    ):
        db.add(
            UnloadingItemRate(
                vendor_division_id=division.id,
                item_code=code,
                item_name=name,
                base_rate=Decimal(base),
                per_floor_rate=Decimal(floor_rate),
                driver_base_rate=Decimal(d_base),
                driver_per_floor_rate=Decimal(d_floor),
                effective_from=date(2026, 4, 1),
                is_active=True,
            )
        )

    owner = VehicleOwner(name="Target Express", phone="9000000061", is_active=True)
    db.add(owner)
    db.flush()
    vehicle = Vehicle(
        owner_id=owner.id, registration_no="KL07CW3317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Rajesh K", phone="9000000060", user_id=user.id, is_active=True)
    consignee = Consignee(
        name="Anand Agencies",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([vehicle, driver, consignee])
    db.flush()

    freight = Freight(
        trip_no="Y26009501",
        trip_date=date.today(),
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.IN_TRANSIT,
        point_count=1,
        total_km=120,
    )
    db.add(freight)
    db.flush()
    point = FreightPoint(
        freight_id=freight.id,
        sequence=1,
        consignee_id=consignee.id,
        loaded_box_count=5,
        floor_number=2,
        has_lift=False,
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

    # Five chairs on the bill.
    consignment = Consignment(
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        consignee_id=consignee.id,
        freight_point_id=point.id,
        vendor_bill_no="GDJ/9501",
        bill_date=date.today(),
        declared_box_count=5,
    )
    db.add(consignment)
    db.flush()
    for n in range(1, 6):
        db.add(
            Box(
                consignment_id=consignment.id,
                item_no=n,
                barcode=f"TE-UNL01-{n:03d}",
                item_code="CHAIR",
                item_name="Chair",
                status=BoxStatus.LOADED,
            )
        )

    db.commit()
    data = {
        "point": str(point.id),
        "freight": str(freight.id),
        "division": str(division.id),
        "headers": {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"},
    }
    db.close()
    return data


def _sheet(client, door, **params):
    return client.get(
        f"/api/driver/points/{door['point']}/unloading",
        params=params,
        headers=door["headers"],
    )


def _log(client, door, **body):
    return client.post(
        f"/api/driver/points/{door['point']}/unloading",
        json=body,
        headers=door["headers"],
    )


# ---------------------------------------------------------------------------
# What the phone is shown
# ---------------------------------------------------------------------------


def test_the_articles_come_priced_for_this_door(client, door):
    """Second floor, no lift: a chair is 50 + 2x10 to the vendor and 30 + 2x6
    to the driver. Sent already worked out, so the phone needs to know nothing
    about rate cards."""
    body = _sheet(client, door).json()

    assert body["floor_number"] == 2
    assert body["priced_per_article"] is True

    chair = next(a for a in body["articles"] if a["item_code"] == "CHAIR")
    assert Decimal(chair["vendor_each"]) == Decimal("70.00")
    assert Decimal(chair["driver_each"]) == Decimal("42.00")


def test_changing_the_floor_reprices_without_saving(client, door):
    """He finds out it is the fourth floor when he gets there. Looking must not
    change what the vendor is charged."""
    body = _sheet(client, door, floor=4).json()
    chair = next(a for a in body["articles"] if a["item_code"] == "CHAIR")
    assert Decimal(chair["vendor_each"]) == Decimal("90.00")

    assert _sheet(client, door).json()["floor_number"] == 2, "merely looking saved a floor"


def test_a_lift_cancels_the_climb_on_both_sides(client, door):
    body = _sheet(client, door, floor=4, lift=True).json()
    chair = next(a for a in body["articles"] if a["item_code"] == "CHAIR")
    assert Decimal(chair["vendor_each"]) == Decimal("50.00")
    assert Decimal(chair["driver_each"]) == Decimal("30.00")


# ---------------------------------------------------------------------------
# Logging it
# ---------------------------------------------------------------------------


def test_logging_what_he_carried_prices_both_sides(client, door):
    res = _log(client, door, articles=[{"item_code": "CHAIR", "quantity": 4}])
    assert res.status_code == 200, res.text

    body = res.json()
    assert Decimal(body["vendor_total"]) == Decimal("280.00"), "4 x 70"
    assert Decimal(body["driver_total"]) == Decimal("168.00"), "4 x 42"


def test_the_floor_he_reports_is_the_one_priced(client, door):
    """He is at the door. The trip was planned by somebody who was not."""
    body = _log(
        client,
        door,
        articles=[{"item_code": "CHAIR", "quantity": 2}],
        floor_number=4,
    ).json()

    assert body["floor_number"] == 4
    assert Decimal(body["vendor_total"]) == Decimal("180.00"), "2 x (50 + 4x10)"


def test_a_corrected_quantity_goes_down(client, door):
    """Four, then three. Merging rather than replacing would leave it at four
    and overcharge the vendor."""
    _log(client, door, articles=[{"item_code": "CHAIR", "quantity": 4}])
    body = _log(client, door, articles=[{"item_code": "CHAIR", "quantity": 3}]).json()

    assert Decimal(body["vendor_total"]) == Decimal("210.00")
    chair = next(a for a in body["articles"] if a["item_code"] == "CHAIR")
    assert chair["quantity"] == 3


def test_the_log_comes_back_when_he_reopens_it(client, door):
    _log(client, door, articles=[{"item_code": "CHAIR", "quantity": 4}])
    chair = next(a for a in _sheet(client, door).json()["articles"] if a["item_code"] == "CHAIR")
    assert chair["quantity"] == 4


def test_an_article_this_vendor_does_not_pay_for_is_refused(client, door):
    res = _log(client, door, articles=[{"item_code": "PIANO", "quantity": 1}])
    assert res.status_code == 422
    assert "PIANO" in res.json()["detail"]


def test_a_refused_log_changes_nothing(client, door):
    _log(client, door, articles=[{"item_code": "CHAIR", "quantity": 4}])
    _log(client, door, articles=[{"item_code": "PIANO", "quantity": 1}])

    body = _sheet(client, door).json()
    assert Decimal(body["vendor_total"]) == Decimal("280.00"), "the good log was lost"


# ---------------------------------------------------------------------------
# Coolie, which is not unloading
# ---------------------------------------------------------------------------


def test_the_driver_can_log_the_porter_cash(client, door):
    body = _log(
        client,
        door,
        articles=[{"item_code": "CHAIR", "quantity": 4}],
        coolie_paid="150",
        coolie_note="Market gang at the gate would not let us unload",
    ).json()

    assert Decimal(body["coolie_paid"]) == Decimal("150")
    assert "gate" in body["coolie_note"]


def test_coolie_is_not_folded_into_unloading(client, door):
    """Folding it in makes the unloading sheet look wrong and makes "why has
    unloading gone up?" unanswerable three weeks later."""
    body = _log(
        client,
        door,
        articles=[{"item_code": "CHAIR", "quantity": 4}],
        coolie_paid="150",
    ).json()
    assert Decimal(body["vendor_total"]) == Decimal("280.00"), "coolie leaked into unloading"


# ---------------------------------------------------------------------------
# What the invoice then reads
# ---------------------------------------------------------------------------


class _PerArticleCard:
    """Just enough of a rate card to say how unloading is priced."""

    from app.models.enums import UnloadingBasis as _B

    unloading_basis = _B.PER_ITEM_FLOOR
    unloading_rate = Decimal("0")


def _billable(freight_id: str) -> Decimal:
    from app.db.session import SessionLocal
    from app.models.freight import Freight
    from app.services.invoicing import billable_unloading

    db = SessionLocal()
    try:
        return billable_unloading(db, db.get(Freight, freight_id), _PerArticleCard)
    finally:
        db.close()


def test_without_a_log_the_bill_is_priced_from_the_boxes(client, door):
    """The fallback. Charging zero because a driver forgot is worse than
    charging from the paperwork, and the paperwork is usually right."""
    assert _billable(door["freight"]) == Decimal("350.00"), "5 chairs x 70"


def test_the_drivers_log_beats_the_paperwork(client, door):
    """The whole point. Five on the bill, four carried in, one refused at the
    door — the vendor is charged for four."""
    _log(client, door, articles=[{"item_code": "CHAIR", "quantity": 4}])
    assert _billable(door["freight"]) == Decimal("280.00")


def test_a_log_is_never_topped_up_from_the_boxes(client, door):
    """One chair logged against five on the bill is exactly the case this
    exists to capture. Making up the difference would throw it away."""
    _log(client, door, articles=[{"item_code": "CHAIR", "quantity": 1}])
    assert _billable(door["freight"]) == Decimal("70.00")


def test_logging_an_article_the_boxes_never_mentioned(client, door):
    """A wardrobe went in that the bill recorded as a chair. He carried a
    wardrobe."""
    _log(client, door, articles=[{"item_code": "WARDROBE", "quantity": 1}])
    assert _billable(door["freight"]) == Decimal("560.00"), "400 + 2x80"


# ---------------------------------------------------------------------------
# Who may write it
# ---------------------------------------------------------------------------


def test_another_drivers_stop_is_refused(client, door):
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.fleet import Driver
    from app.models.user import User

    db = SessionLocal()
    other = User(
        full_name="Someone Else",
        phone="9000000062",
        role=UserRole.DRIVER,
        hashed_password=hash_password("x"),
        is_active=True,
    )
    db.add(other)
    db.flush()
    db.add(Driver(name="Someone Else", phone="9000000062", user_id=other.id, is_active=True))
    db.commit()
    token = create_access_token(str(other.id), other.role)
    db.close()

    res = client.post(
        f"/api/driver/points/{door['point']}/unloading",
        json={"articles": [{"item_code": "CHAIR", "quantity": 9}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_an_invoiced_trip_cannot_be_relogged(client, door):
    """It would make the invoice disagree with the trip it was built from."""
    from app.db.session import SessionLocal
    from app.models.enums import FreightStatus
    from app.models.freight import Freight

    db = SessionLocal()
    db.get(Freight, door["freight"]).status = FreightStatus.BILLED
    db.commit()
    db.close()

    res = _log(client, door, articles=[{"item_code": "CHAIR", "quantity": 4}])
    assert res.status_code == 409
    assert "invoiced" in res.json()["detail"]


def test_the_sheet_needs_a_driver_login(client, door):
    assert client.get(f"/api/driver/points/{door['point']}/unloading").status_code == 401


def test_a_driver_who_is_not_paid_by_us_is_not_shown_a_figure(client, door):
    """A driver on a rented vehicle is paid by the vehicle's owner, not by
    Target Express. Showing him a rate here would be money he never sees.

    Zeroed on the server rather than hidden by the screen: a number that must
    not be shown should not be sent.
    """
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.fleet import Driver
    from app.models.freight import FreightLeg
    from app.models.user import User
    from sqlalchemy import select

    db = SessionLocal()
    hired = User(
        full_name="Basheer C",
        phone="9000000063",
        role=UserRole.DRIVER,
        hashed_password=hash_password("x"),
        is_active=True,
        can_view_earnings=False,
    )
    db.add(hired)
    db.flush()
    driver = Driver(name="Basheer C", phone="9000000063", user_id=hired.id, is_active=True)
    db.add(driver)
    db.flush()
    # Put him on the trip, or he is refused before the figure is even reached.
    leg = db.execute(select(FreightLeg)).scalars().first()
    leg.driver_id = driver.id
    db.commit()
    token = create_access_token(str(hired.id), hired.role)
    db.close()

    body = client.get(
        f"/api/driver/points/{door['point']}/unloading",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert body["shows_earnings"] is False
    assert all(Decimal(a["driver_each"]) == 0 for a in body["articles"])
    assert Decimal(body["driver_total"]) == 0
    # The vendor's side is still his business — he has to log the articles.
    chair = next(a for a in body["articles"] if a["item_code"] == "CHAIR")
    assert Decimal(chair["vendor_each"]) == Decimal("70.00")
