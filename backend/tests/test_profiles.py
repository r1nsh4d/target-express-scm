"""One lorry, or one driver, with everything about it in one place.

The list answers "which vehicles do we have". Nobody asks that. They ask about
one lorry: how much has it run, what did it earn against what it cost, who
drives it. Or about one driver: what has he run, what is he owed, what has
already been settled, what is outstanding against him.

Three things these tests hold, because each is a way the figures can quietly
come out wrong:

  * A TWO-LEG TRIP IS ONE INVOICE. A breakdown splits a trip across two
    vehicles. The kilometres split with them; the invoice line does not, and
    counting it once per leg would credit a lorry with money twice.
  * A DRIVER'S PAY IS NOT A VEHICLE'S COST. An owned lorry pays its driver, a
    rented one pays the vehicle's owner, and the payout model records the
    driver on every row regardless so the document can name him. Reading
    those rows as the driver's earnings would pay a man on paper for money
    that went to somebody else.
  * SETTLED AND UNSETTLED ARE DIFFERENT QUESTIONS. What he has earned is not
    what he is owed; the gap is the part already covered by a settlement, and
    it is the only figure anybody acts on.
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
    "rate_cards",
    "freights",
    "freight_points",
    "freight_legs",
    "trip_expenses",
    "vendor_invoices",
    "vendor_invoice_lines",
    "settlements",
    "freight_payouts",
    "advances",
)

TODAY = date.today()
TRIP_DAY = TODAY - timedelta(days=5)


@pytest.fixture()
def scene(client, auth):
    """One lorry, one driver, two trips — the second broken down mid-route."""
    from app.db.session import SessionLocal
    from app.models.billing import VendorInvoice, VendorInvoiceLine
    from app.models.consignee import Consignee
    from app.models.enums import (
        ChargeHead,
        ConsigneeType,
        FreightStatus,
        GeoConfidence,
        InvoiceStatus,
        PayeeType,
    )
    from app.models.fleet import Driver, Vehicle, VehicleOwner, VehicleType
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.settlement import Advance, FreightPayout
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
    dost = VehicleType(name="DOST", capacity_kg=1250)
    db.add_all([division, warehouse, dost])
    db.flush()

    owner = VehicleOwner(name="Target Express", phone="9000000041", is_active=True)
    db.add(owner)
    db.flush()
    lorry = Vehicle(
        owner_id=owner.id,
        vehicle_type_id=dost.id,
        registration_no="KL07CW3317",
        lr_next_number=774,
        last_closing_km=239673,
        is_active=True,
    )
    spare = Vehicle(
        owner_id=owner.id, registration_no="KL41U0317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Suresh", phone="9000000032", is_active=True)
    other_driver = Driver(name="Shaji", phone="9000000033", is_active=True)
    consignee = Consignee(
        name="Kannur Distribution Centre",
        type=ConsigneeType.DISTRIBUTION_CENTER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([lorry, spare, driver, other_driver, consignee])
    db.flush()

    invoice = VendorInvoice(
        invoice_no="191/2026-27/001",
        invoice_date=TODAY,
        period_from=TRIP_DAY,
        period_to=TODAY,
        vendor_division_id=division.id,
        taxable_value=Decimal("5000"),
        total=Decimal("5600"),
        status=InvoiceStatus.ISSUED,
    )
    db.add(invoice)
    db.flush()

    freights = []
    for n, (km, invoiced) in enumerate([(100, Decimal("2000")), (200, Decimal("3000"))]):
        freight = Freight(
            trip_no=f"Y2600900{n + 1}",
            trip_date=TRIP_DAY + timedelta(days=n),
            vendor_division_id=division.id,
            warehouse_id=warehouse.id,
            status=FreightStatus.COMPLETED,
            point_count=2,
            total_km=km,
            lr_no=str(774 + n),
            destination_text="Kannur",
        )
        db.add(freight)
        db.flush()
        db.add(FreightPoint(freight_id=freight.id, sequence=1, consignee_id=consignee.id))
        db.add(
            VendorInvoiceLine(
                invoice_id=invoice.id,
                freight_id=freight.id,
                sl_no=n + 1,
                trip_date=freight.trip_date,
                trip_no=freight.trip_no,
                vehicle_no=lorry.registration_no,
                destination_text="Kannur",
                point_count=2,
                km=km,
                line_total=invoiced,
            )
        )
        freights.append(freight)

    # Trip one: the whole 100 km on the lorry, Suresh driving.
    db.add(
        FreightLeg(
            freight_id=freights[0].id,
            sequence=1,
            vehicle_id=lorry.id,
            driver_id=driver.id,
            start_odometer=1000,
            end_odometer=1100,
            leg_distance_km=100,
        )
    )
    # Trip two: breaks down at 120 km, the spare finishes the last 80.
    db.add(
        FreightLeg(
            freight_id=freights[1].id,
            sequence=1,
            vehicle_id=lorry.id,
            driver_id=driver.id,
            start_odometer=1100,
            end_odometer=1220,
            leg_distance_km=120,
        )
    )
    db.add(
        FreightLeg(
            freight_id=freights[1].id,
            sequence=2,
            vehicle_id=spare.id,
            driver_id=other_driver.id,
            start_odometer=5000,
            end_odometer=5080,
            leg_distance_km=80,
        )
    )
    db.flush()

    legs = {
        (leg.freight_id, leg.sequence): leg
        for leg in db.execute(__import__("sqlalchemy").select(FreightLeg)).scalars().all()
    }

    # Suresh's pay. Both unsettled to begin with; one test settles the first.
    for freight, leg_key, amount in [
        (freights[0], (freights[0].id, 1), Decimal("250")),
        (freights[1], (freights[1].id, 1), Decimal("300")),
    ]:
        db.add(
            FreightPayout(
                freight_id=freight.id,
                leg_id=legs[leg_key].id,
                head=ChargeHead.TRANSPORTATION,
                payee_type=PayeeType.DRIVER,
                driver_id=driver.id,
                vehicle_id=lorry.id,
                amount=amount,
                settlement_id=None,
            )
        )
    db.add(
        FreightPayout(
            freight_id=freights[0].id,
            leg_id=legs[(freights[0].id, 1)].id,
            head=ChargeHead.LOADING_UNLOADING,
            payee_type=PayeeType.DRIVER,
            driver_id=driver.id,
            vehicle_id=lorry.id,
            amount=Decimal("140"),
        )
    )
    # Money that went to the vehicle's owner, with Suresh named on the row.
    # His earnings must not include it.
    db.add(
        FreightPayout(
            freight_id=freights[0].id,
            leg_id=legs[(freights[0].id, 1)].id,
            head=ChargeHead.TRANSPORTATION,
            payee_type=PayeeType.VEHICLE_OWNER,
            driver_id=driver.id,
            vehicle_owner_id=owner.id,
            vehicle_id=lorry.id,
            amount=Decimal("900"),
        )
    )

    db.add(
        Advance(
            payee_type=PayeeType.DRIVER,
            driver_id=driver.id,
            advance_date=TRIP_DAY,
            amount=Decimal("1000"),
            recovered_amount=Decimal("400"),
            reason="Diesel at Thrissur",
        )
    )
    db.commit()

    data = {
        "lorry": str(lorry.id),
        "spare": str(spare.id),
        "driver": str(driver.id),
        "freights": [str(f.id) for f in freights],
    }
    db.close()
    return data


# ---------------------------------------------------------------------------
# The vehicle
# ---------------------------------------------------------------------------


def test_the_lorry_carries_its_own_identity(client, scene, auth):
    res = client.get(f"/api/vehicles/{scene['lorry']}/profile", headers=auth)
    assert res.status_code == 200, res.text

    profile = res.json()
    assert profile["registration_no"] == "KL07CW3317"
    assert profile["vehicle_type_name"] == "DOST"
    assert profile["last_closing_km"] == 239673
    assert profile["lr_next_number"] == 774


def test_a_lorry_counts_only_the_kilometres_it_ran(client, scene, auth):
    """The spare finished the second trip, so 80 of its 200 are not this one's."""
    profile = client.get(f"/api/vehicles/{scene['lorry']}/profile", headers=auth).json()
    assert profile["km"] == 220
    assert profile["trips"] == 2

    spare = client.get(f"/api/vehicles/{scene['spare']}/profile", headers=auth).json()
    assert spare["km"] == 80
    assert spare["trips"] == 1


def test_a_two_leg_trip_is_not_invoiced_twice_against_one_lorry(client, scene, auth):
    """2,000 plus 3,000, not 2,000 plus 3,000 plus 3,000."""
    profile = client.get(f"/api/vehicles/{scene['lorry']}/profile", headers=auth).json()
    assert Decimal(profile["invoiced"]) == Decimal("5000.00")


def test_the_lorry_costs_what_was_paid_out_against_it(client, scene, auth):
    """Every payout naming this vehicle: 250 + 300 + 140 to Suresh, 900 to the owner."""
    profile = client.get(f"/api/vehicles/{scene['lorry']}/profile", headers=auth).json()
    assert Decimal(profile["cost"]) == Decimal("1590.00")
    assert Decimal(profile["margin"]) == Decimal("3410.00")
    # 3410 over 220 km.
    assert Decimal(profile["margin_per_km"]) == Decimal("15.50")


def test_the_lorry_lists_its_runs_and_its_drivers(client, scene, auth):
    profile = client.get(f"/api/vehicles/{scene['lorry']}/profile", headers=auth).json()
    assert [r["trip_no"] for r in profile["runs"]] == ["Y26009002", "Y26009001"]
    assert profile["drivers"] == ["Suresh"]
    assert profile["first_trip"] == TRIP_DAY.isoformat()


def test_a_lorry_that_has_never_run_does_not_divide_by_zero(client, scene, auth):
    from app.db.session import SessionLocal
    from app.models.fleet import Vehicle

    db = SessionLocal()
    try:
        fresh = Vehicle(registration_no="KL99XX9999", lr_next_number=1, is_active=True)
        db.add(fresh)
        db.commit()
        fresh_id = str(fresh.id)
    finally:
        db.close()

    profile = client.get(f"/api/vehicles/{fresh_id}/profile", headers=auth).json()
    assert profile["trips"] == 0
    assert Decimal(profile["margin_per_km"]) == Decimal("0.00")
    assert profile["runs"] == []


# ---------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------


def test_a_driver_earns_only_what_was_paid_to_him(client, scene, auth):
    """The 900 went to the vehicle's owner, with his name on the row."""
    res = client.get(f"/api/drivers/{scene['driver']}/profile", headers=auth)
    assert res.status_code == 200, res.text

    profile = res.json()
    assert Decimal(profile["earned"]) == Decimal("690.00")
    assert Decimal(profile["transportation"]) == Decimal("550.00")
    assert Decimal(profile["unloading"]) == Decimal("140.00")


def test_what_he_is_owed_is_the_unsettled_part(client, scene, auth):
    """Earned is history. Unsettled is the number anybody acts on."""
    profile = client.get(f"/api/drivers/{scene['driver']}/profile", headers=auth).json()
    assert Decimal(profile["settled"]) == Decimal("0.00")
    assert Decimal(profile["unsettled"]) == Decimal("690.00")


def test_a_settled_payout_moves_out_of_what_he_is_owed(client, scene, auth):
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
            driver_id=scene["driver"],
            trip_count=1,
            gross_amount=Decimal("390"),
            net_payable=Decimal("390"),
            status=SettlementStatus.PAID,
        )
        db.add(settlement)
        db.flush()
        for payout in (
            db.execute(
                __import__("sqlalchemy")
                .select(FreightPayout)
                .where(FreightPayout.freight_id == scene["freights"][0])
                .where(FreightPayout.payee_type == PayeeType.DRIVER)
            )
            .scalars()
            .all()
        ):
            payout.settlement_id = settlement.id
        db.commit()
    finally:
        db.close()

    profile = client.get(f"/api/drivers/{scene['driver']}/profile", headers=auth).json()
    assert Decimal(profile["settled"]) == Decimal("390.00")
    assert Decimal(profile["unsettled"]) == Decimal("300.00")
    assert [s["settlement_no"] for s in profile["settlements"]] == ["S/001"]


def test_an_outstanding_advance_is_what_is_left_of_it(client, scene, auth):
    """1,000 handed over, 400 recovered, 600 still against him."""
    profile = client.get(f"/api/drivers/{scene['driver']}/profile", headers=auth).json()
    assert Decimal(profile["advances_outstanding"]) == Decimal("600.00")
    assert profile["advances"][0]["reason"] == "Diesel at Thrissur"


def test_a_driver_lists_his_runs_and_his_lorries(client, scene, auth):
    profile = client.get(f"/api/drivers/{scene['driver']}/profile", headers=auth).json()
    assert profile["trips"] == 2
    assert profile["km"] == 220
    assert profile["vehicles"] == ["KL07CW3317"]
    assert [r["counterpart"] for r in profile["runs"]] == ["KL07CW3317", "KL07CW3317"]


def test_an_unknown_driver_is_a_404(client, auth):
    import uuid

    assert (
        client.get(f"/api/drivers/{uuid.uuid4()}/profile", headers=auth).status_code == 404
    )
