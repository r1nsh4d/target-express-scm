"""The reading that became a ₹34 lakh invoice.

An invoice went to Godrej for ₹34,28,434.24 on a single one-point run to
Aluva. The line read 180,015 km at ₹17 a kilometre beyond the sixty included.
180,015 is not a distance — it is what the lorry's odometer says, and it went
in as the closing reading of a leg whose opening reading was near zero.

Nothing objected anywhere along the way. Not the phone that took the reading,
not the office screen, not the invoice preview. The number was four and a half
times round the Earth and it printed, was signed, and went out.

Three layers, because one is not enough:

  * THE PHONE refuses a meter that runs backwards, and a pair of readings
    that cannot be one run.
  * THE OFFICE CORRECTION is the other way a distance gets set, and it was
    the unguarded one.
  * THE INVOICE leaves such a freight OFF the bill, because the readings
    already in the database are not fixed by guarding new ones — and the next
    sweep would bill them exactly as the first did.

Every refusal names both readings and the distance they imply. "Too far"
sends somebody hunting; "closing 180,015 against opening 60" tells them which
of the two they fat-fingered.
"""

from __future__ import annotations

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
    "odometer_corrections",
    "tracking_sessions",
    "vehicle_pings",
    "audit_logs",
)

TODAY = date.today()
TRIP_DAY = TODAY - timedelta(days=1)


@pytest.fixture()
def run(client, auth):
    """A dispatched one-point run to Aluva, on a lorry reading 180,015."""
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence, UserRole
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.rating import RateCard
    from app.models.user import User
    from app.models.vendor import Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()

    vendor = Vendor(name="Godrej", payment_terms_days=30, is_active=True)
    db.add(vendor)
    db.flush()
    division = VendorDivision(
        vendor_id=vendor.id,
        name="Godrej Appliance Spare",
        code="GODREJ-SPARE",
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
    # The real reading on the real lorry from the invoice.
    lorry = Vehicle(
        owner_id=owner.id,
        registration_no="KL10AL4477",
        lr_next_number=901,
        last_closing_km=180_015,
        is_active=True,
    )
    user = User(
        full_name="Driver",
        phone="9000000501",
        role=UserRole.DRIVER,
        hashed_password=hash_password("x"),
        is_active=True,
        can_view_earnings=True,
    )
    db.add_all([lorry, user])
    db.flush()
    driver = Driver(name="Driver", phone="9000000501", user_id=user.id, is_active=True)
    consignee = Consignee(
        name="Aluva Dealer",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Aluva",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([driver, consignee])
    db.flush()

    freight = Freight(
        trip_no="Y26000008",
        trip_date=TRIP_DAY,
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.PLANNED,
        point_count=1,
        destination_text="Aluva (1PT)",
    )
    db.add(freight)
    db.flush()
    db.add(FreightPoint(freight_id=freight.id, sequence=1, consignee_id=consignee.id))
    leg = FreightLeg(
        freight_id=freight.id, sequence=1, vehicle_id=lorry.id, driver_id=driver.id
    )
    db.add(leg)
    db.commit()

    data = {
        "division": str(division.id),
        "freight": str(freight.id),
        "leg": str(leg.id),
        "headers": {
            "Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"
        },
    }
    db.close()
    return data


def _start(client, run, reading):
    return client.post(
        f"/api/driver/legs/{run['leg']}/start",
        json={"reading": reading},
        headers=run["headers"],
    )


def _close(client, run, reading):
    return client.post(
        f"/api/driver/legs/{run['leg']}/close",
        json={"reading": reading},
        headers=run["headers"],
    )


# ---------------------------------------------------------------------------
# The phone
# ---------------------------------------------------------------------------


def test_the_meter_cannot_run_backwards(client, run):
    """He taps 60 on a lorry that finished its last run at 180,015."""
    res = _start(client, run, 60)

    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "180,015" in detail
    assert "backwards" in detail


def test_a_normal_opening_reading_is_fine(client, run):
    assert _start(client, run, 180_015).status_code == 204


def test_a_lorry_with_no_history_is_not_second_guessed(client, run):
    """A vehicle added today has no last closing reading, and refusing its
    first trip over a number nobody has yet is worse than taking it."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.fleet import Vehicle

    db = SessionLocal()
    try:
        db.execute(select(Vehicle)).scalars().first().last_closing_km = None
        db.commit()
    finally:
        db.close()

    assert _start(client, run, 60).status_code == 204


def test_the_run_that_produced_the_invoice_is_refused(client, run):
    """Opening near zero, then the real meter as the closing reading."""
    assert _start(client, run, 60).status_code == 409

    # Even with the opening accepted — a lorry with no history — the pair is
    # still impossible as one run.
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.fleet import Vehicle

    db = SessionLocal()
    try:
        db.execute(select(Vehicle)).scalars().first().last_closing_km = None
        db.commit()
    finally:
        db.close()

    _start(client, run, 60)
    res = _close(client, run, 180_015)

    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "179,955 km" in detail
    assert "180,015" in detail and "60" in detail


def test_an_ordinary_round_trip_closes_normally(client, run):
    _start(client, run, 180_015)
    assert _close(client, run, 180_115).status_code == 204


def test_a_closing_reading_below_the_opening_is_refused(client, run):
    _start(client, run, 180_015)
    res = _close(client, run, 179_000)

    assert res.status_code == 409
    assert "below the opening" in res.json()["detail"]


def test_a_kasaragod_round_trip_is_still_allowed(client, run):
    """Ernakulam to Kasaragod and back is about 950 km. A guard that argues
    with a real long day gets switched off."""
    _start(client, run, 180_015)
    assert _close(client, run, 180_015 + 950).status_code == 204


# ---------------------------------------------------------------------------
# The office correction, which was the unguarded path
# ---------------------------------------------------------------------------


def test_a_correction_cannot_create_an_impossible_distance(client, run, auth):
    _start(client, run, 180_015)
    _close(client, run, 180_115)

    res = client.post(
        f"/api/freights/{run['freight']}/legs/{run['leg']}/correct-odometer",
        json={"field": "start_odometer", "corrected_value": 60, "reason": "typo"},
        headers=auth,
    )
    assert res.status_code == 409
    assert "180,115" in res.json()["detail"]


def test_an_ordinary_correction_still_works(client, run, auth):
    _start(client, run, 180_015)
    _close(client, run, 180_115)

    res = client.post(
        f"/api/freights/{run['freight']}/legs/{run['leg']}/correct-odometer",
        json={"field": "end_odometer", "corrected_value": 180_135, "reason": "misread"},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert res.json()["total_km"] == 120


# ---------------------------------------------------------------------------
# The invoice, for the freights already carrying a bad figure
# ---------------------------------------------------------------------------


def _bad_freight(freight_id: str, km: int) -> None:
    """Force the state the real database is already in."""
    from app.db.session import SessionLocal
    from app.models.enums import FreightStatus
    from app.models.freight import Freight

    db = SessionLocal()
    try:
        freight = db.get(Freight, freight_id)
        freight.total_km = km
        freight.status = FreightStatus.COMPLETED
        db.commit()
    finally:
        db.close()


def _preview(client, auth, run):
    return client.post(
        "/api/invoices/preview",
        json={
            "vendor_division_id": run["division"],
            "period_from": (TRIP_DAY - timedelta(days=1)).isoformat(),
            "period_to": TODAY.isoformat(),
        },
        headers=auth,
    ).json()


def test_a_freight_with_an_impossible_distance_is_kept_off_the_invoice(
    client, run, auth
):
    """Guarding new readings does nothing for the ones already stored, and
    the next sweep would bill them exactly as the first one did."""
    _bad_freight(run["freight"], 180_015)

    preview = _preview(client, auth, run)
    assert preview["lines"] == []
    assert any("180,015 km" in p for p in preview["problems"])


def test_the_refusal_says_how_to_make_it_billable(client, run, auth):
    """Refused rather than flagged — a warning above a tick box that is
    already ticked is a warning somebody clicks past."""
    _bad_freight(run["freight"], 180_015)

    problem = _preview(client, auth, run)["problems"][0]
    assert "odometer looks wrong" in problem
    assert "Correct it" in problem


def test_an_ordinary_freight_still_bills(client, run, auth):
    _bad_freight(run["freight"], 100)

    preview = _preview(client, auth, run)
    assert len(preview["lines"]) == 1
    assert preview["problems"] == []
    # 1,867 base + 40 km over 60 at 17 = 2,547.
    assert Decimal(preview["taxable_value"]) == Decimal("2547.00")
