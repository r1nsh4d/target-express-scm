"""A fare agreed for one run, rather than worked out from a standing rate.

Per-kilometre pay is right for the ordinary case and wrong for the ones people
actually ring about. A Kasaragod round trip is settled as "twelve hundred for
the run" before the lorry leaves; a short town job is "two fifty and that is
that". There was nowhere to put either, so the real figure stayed in a
notebook — and once the real figure is in a notebook, the settlement screen is
decoration.

Four things these hold:

  * AN AGREED FIGURE REPLACES THE CALCULATION, rather than adding to it. That
    is what the word means: somebody looked at the job and said what it was
    worth.
  * ZERO IS NOT "WORK IT OUT". A run that pays nothing for driving happens
    when a driver is being squared up another way, and conflating the two
    would silently stop paying everybody.
  * A DRIVER IS STILL NEVER LEFT OUT OF POCKET. An agreement about what the
    work is worth is not an agreement that he funds the labourers himself, so
    the unloading figure is floored at what he actually handed over.
  * A SETTLED RUN IS FROZEN. Its payouts are inside a settlement somebody has
    been paid against; moving the figure underneath would leave the document
    disagreeing with its own lines.
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
    "vehicle_types",
    "vehicle_owners",
    "vehicles",
    "vehicle_hire_terms",
    "drivers",
    "driver_pay_terms",
    "rate_cards",
    "unloading_item_rates",
    "freights",
    "freight_points",
    "freight_legs",
    "point_unloading_items",
    "consignments",
    "boxes",
    "trip_expenses",
    "vendor_invoices",
    "vendor_invoice_lines",
    "settlements",
    "freight_payouts",
    "advances",
    "tracking_sessions",
    "vehicle_pings",
)

TODAY = date.today()
TRIP_DAY = TODAY - timedelta(days=3)


@pytest.fixture()
def run(client, auth):
    """A closed 100 km run. On the standing rate of 2.50 a km that is 250."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence
    from app.models.fleet import Driver, DriverPayTerms, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.rating import RateCard
    from app.models.vendor import Vendor, VendorDivision, VendorWarehouse
    from app.services.completion import record_leg_payouts

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
    db.add(
        RateCard(
            vendor_division_id=division.id,
            base_trip_amount=Decimal("1867"),
            included_km=60,
            included_points=3,
            extra_km_rate=Decimal("17"),
            extra_point_rate=Decimal("175"),
            effective_from=TRIP_DAY - timedelta(days=30),
            is_active=True,
        )
    )

    owner = VehicleOwner(name="Target Express", phone="9000000041", is_active=True)
    db.add(owner)
    db.flush()
    lorry = Vehicle(
        owner_id=owner.id, registration_no="KL07CW3317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Anil P", phone="9000000012", is_active=True)
    consignee = Consignee(
        name="Kannur Distribution Centre",
        type=ConsigneeType.DISTRIBUTION_CENTER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([lorry, driver, consignee])
    db.flush()
    db.add(
        DriverPayTerms(
            driver_id=driver.id,
            per_km_amount=Decimal("2.50"),
            effective_from=TRIP_DAY - timedelta(days=30),
        )
    )

    freight = Freight(
        trip_no="Y26009001",
        trip_date=TRIP_DAY,
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.COMPLETED,
        point_count=1,
        total_km=100,
    )
    db.add(freight)
    db.flush()
    point = FreightPoint(
        freight_id=freight.id,
        sequence=1,
        consignee_id=consignee.id,
        unloading_paid=Decimal("0"),
    )
    leg = FreightLeg(
        freight_id=freight.id,
        sequence=1,
        vehicle_id=lorry.id,
        driver_id=driver.id,
        start_odometer=1000,
        end_odometer=1100,
        leg_distance_km=100,
    )
    db.add_all([point, leg])
    db.flush()
    record_leg_payouts(db, leg)
    db.commit()

    data = {
        "freight": str(freight.id),
        "leg": str(leg.id),
        "point": str(point.id),
        "driver": str(driver.id),
    }
    db.close()
    return data


def _set(client, auth, run, **body):
    return client.post(
        f"/api/freights/{run['freight']}/legs/{run['leg']}/fare",
        json=body,
        headers=auth,
    )


def _cost(client, auth, run):
    return client.get(f"/api/freights/{run['freight']}/economics", headers=auth).json()


# ---------------------------------------------------------------------------
# The fare
# ---------------------------------------------------------------------------


def test_without_an_agreement_the_standing_rate_applies(client, run, auth):
    """100 km at 2.50. The ordinary case, unchanged."""
    cost = _cost(client, auth, run)
    driving = next(line for line in cost["cost"] if line["label"] == "Driving")

    assert Decimal(driving["amount"]) == Decimal("250.00")
    assert "2.5" in driving["working"]


def test_an_agreed_fare_replaces_the_distance_calculation(client, run, auth):
    """Twelve hundred for the run, not twelve hundred plus the kilometres."""
    assert _set(client, auth, run, fare="1200", set_unloading=False).status_code == 200

    cost = _cost(client, auth, run)
    driving = next(line for line in cost["cost"] if line["label"] == "Driving")

    assert Decimal(driving["amount"]) == Decimal("1200.00")
    assert Decimal(cost["cost_total"]) == Decimal("1200.00")


def test_the_line_says_it_was_agreed_rather_than_calculated(client, run, auth):
    """A settlement document must not claim arithmetic nobody did."""
    _set(client, auth, run, fare="1200", set_unloading=False)

    driving = next(
        line for line in _cost(client, auth, run)["cost"] if line["label"] == "Driving"
    )
    assert "agreed fare" in driving["working"]
    assert "100 km" in driving["working"]
    assert "2.5" not in driving["working"]


def test_a_fare_of_zero_is_an_answer_not_a_blank(client, run, auth):
    """A run paying nothing for driving is a real thing on a day a driver is
    being squared up another way. Treating it as "work it out" would silently
    pay him the per-km figure he was not promised."""
    assert _set(client, auth, run, fare="0", set_unloading=False).status_code == 200
    assert Decimal(_cost(client, auth, run)["cost_total"]) == Decimal("0.00")


def test_clearing_the_agreement_goes_back_to_the_rate(client, run, auth):
    _set(client, auth, run, fare="1200", set_unloading=False)
    assert _set(client, auth, run, fare=None, set_unloading=False).status_code == 200

    assert Decimal(_cost(client, auth, run)["cost_total"]) == Decimal("250.00")


def test_leaving_a_field_out_does_not_touch_it(client, run, auth):
    """Setting the unloading must not quietly wipe an agreed fare."""
    _set(client, auth, run, fare="1200", set_unloading=False)
    _set(client, auth, run, unloading="300", set_fare=False)

    cost = _cost(client, auth, run)
    driving = next(line for line in cost["cost"] if line["label"] == "Driving")
    assert Decimal(driving["amount"]) == Decimal("1200.00")


# ---------------------------------------------------------------------------
# The unloading
# ---------------------------------------------------------------------------


def test_unloading_can_be_typed_for_a_run_that_prices_it_no_other_way(
    client, run, auth
):
    """This division has no article rates and he is on no percentage, so he
    was being paid nothing at all for carrying goods in."""
    assert Decimal(_cost(client, auth, run)["cost_total"]) == Decimal("250.00")

    assert _set(client, auth, run, unloading="300", set_fare=False).status_code == 200

    cost = _cost(client, auth, run)
    unloading = next(line for line in cost["cost"] if line["label"] == "Unloading")
    assert Decimal(unloading["amount"]) == Decimal("300.00")
    assert Decimal(cost["cost_total"]) == Decimal("550.00")


def test_an_agreed_figure_is_floored_at_what_he_handed_over(client, run, auth):
    """An agreement about what the work is worth is not an agreement that he
    funds the labourers out of his own pocket."""
    from app.db.session import SessionLocal
    from app.models.freight import FreightPoint

    db = SessionLocal()
    try:
        db.get(FreightPoint, run["point"]).unloading_paid = Decimal("450")
        db.commit()
    finally:
        db.close()

    _set(client, auth, run, unloading="300", set_fare=False)

    unloading = next(
        line for line in _cost(client, auth, run)["cost"] if line["label"] == "Unloading"
    )
    assert Decimal(unloading["amount"]) == Decimal("450.00")
    assert "never left out of pocket" in unloading["working"]


# ---------------------------------------------------------------------------
# What it reaches
# ---------------------------------------------------------------------------


def test_the_driver_sees_the_agreed_figure_on_his_phone(client, run, auth):
    """His screen and the office's cost line are one number, agreed or not."""
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.fleet import Driver
    from app.models.user import User

    db = SessionLocal()
    try:
        user = User(
            full_name="Anil P",
            phone="9000000012",
            role=UserRole.DRIVER,
            hashed_password=hash_password("x"),
            is_active=True,
            can_view_earnings=True,
        )
        db.add(user)
        db.flush()
        db.get(Driver, run["driver"]).user_id = user.id
        db.commit()
        headers = {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}
    finally:
        db.close()

    _set(client, auth, run, fare="1200", unloading="300")

    his = client.get(
        f"/api/driver/freights/{run['freight']}/earnings", headers=headers
    ).json()
    assert Decimal(his["total"]) == Decimal("1500.00")
    assert Decimal(his["total"]) == Decimal(_cost(client, auth, run)["cost_total"])


def test_the_payout_rows_are_rewritten_at_once(client, run, auth):
    """So the screen and the settlement cannot drift apart in between."""
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models.settlement import FreightPayout

    _set(client, auth, run, fare="1200", set_unloading=False)

    db = SessionLocal()
    try:
        total = db.scalar(
            select(func.sum(FreightPayout.amount)).where(
                FreightPayout.freight_id == run["freight"]
            )
        )
    finally:
        db.close()
    assert Decimal(total) == Decimal("1200.00")


def test_a_settled_run_refuses_a_new_fare(client, run, auth):
    """Somebody has been paid against those lines."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.enums import PayeeType, SettlementStatus
    from app.models.settlement import FreightPayout, Settlement

    db = SessionLocal()
    try:
        settlement = Settlement(
            settlement_no="S/001",
            settlement_date=TODAY,
            period_from=TRIP_DAY,
            period_to=TODAY,
            payee_type=PayeeType.DRIVER,
            driver_id=run["driver"],
            trip_count=1,
            gross_amount=Decimal("250"),
            net_payable=Decimal("250"),
            status=SettlementStatus.PAID,
        )
        db.add(settlement)
        db.flush()
        for row in (
            db.execute(
                select(FreightPayout).where(FreightPayout.leg_id == run["leg"])
            )
            .scalars()
            .all()
        ):
            row.settlement_id = settlement.id
        db.commit()
    finally:
        db.close()

    res = _set(client, auth, run, fare="1200", set_unloading=False)
    assert res.status_code == 409
    assert "settled" in res.json()["detail"].lower()


def test_the_note_is_kept_with_the_figure(client, run, auth):
    """An amount nobody can explain six weeks later is one that gets queried."""
    _set(
        client,
        auth,
        run,
        fare="1200",
        set_unloading=False,
        note="Agreed with Anil, lorry was going back empty",
    )

    trip = client.get(f"/api/freights/{run['freight']}", headers=auth).json()
    leg = trip["legs"][0]
    assert Decimal(leg["agreed_fare"]) == Decimal("1200.00")
    assert "going back empty" in leg["fare_note"]
