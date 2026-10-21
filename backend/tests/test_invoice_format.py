"""The invoice in the shape the vendor's accounts team already reads.

Target Express's own accountant issues these from Tally. The document that
actually reaches Godrej carries a tax summary split two ways:

    1,56,382.00  at CGST 2.50% + SGST 2.50%  =  3,909.57 + 3,909.57
      2,150.00  at 0%

and the 2,150 is exactly the Toll Charges line. Toll is cash handed to a
booth and recharged at cost, not a service supplied — and we were taxing it,
so every invoice we raised was a little higher than the one their accountant
would have raised for the same work.

Toll alone, deliberately. Coolie is recharged at cost too and their document
taxes it; matching the document they already send beats being clever.

The other two facts in that document the system did not hold: a freight
charge is billed PER VEHICLE TYPE, because a Dost and an Ace are separately
agreed and separately checked; and the GST rate belongs to the invoice rather
than to the division, or changing a division's rate would silently re-rate
every invoice ever raised against it.
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
)

TODAY = date.today()
TRIP_DAY = TODAY - timedelta(days=2)


@pytest.fixture()
def scene(client, auth):
    """Two freights on two vehicle types, one of them carrying a toll.

    Card: 1,867 base covering 60 km. The Dost runs 100 km (40 over, at 17 =
    680) and claims a 2,150 toll. The Ace runs 60 km, nothing extra.
    """
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import (
        ApprovalStatus,
        ConsigneeType,
        EntryMode,
        ExpenseType,
        FreightStatus,
        GeoConfidence,
        PaidBy,
    )
    from app.models.expense import TripExpense
    from app.models.fleet import Driver, Vehicle, VehicleOwner, VehicleType
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.rating import RateCard
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
        # What their accountant charges: 2.5 + 2.5.
        gst_rate_percent=Decimal("5"),
        is_active=True,
    )
    warehouse = VendorWarehouse(vendor_id=vendor.id, name="Kochi", code="KOCHI")
    dost = VehicleType(name="Dost", capacity_kg=1250)
    ace = VehicleType(name="Ace", capacity_kg=750)
    db.add_all([division, warehouse, dost, ace])
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
    lorries = {}
    for code, vtype in (("KL07CW3317", dost), ("KL41U0317", ace)):
        lorry = Vehicle(
            owner_id=owner.id,
            vehicle_type_id=vtype.id,
            registration_no=code,
            lr_next_number=1,
            is_active=True,
        )
        db.add(lorry)
        lorries[vtype.name] = lorry
    driver = Driver(name="Suresh", phone="9000000032", is_active=True)
    consignee = Consignee(
        name="Aluva Dealer",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Aluva",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([driver, consignee])
    db.flush()

    for n, (vtype, km) in enumerate([("Dost", 100), ("Ace", 60)]):
        freight = Freight(
            trip_no=f"Y2601000{n + 1}",
            trip_date=TRIP_DAY,
            vendor_division_id=division.id,
            warehouse_id=warehouse.id,
            status=FreightStatus.COMPLETED,
            point_count=1,
            total_km=km,
            destination_text="Aluva",
        )
        db.add(freight)
        db.flush()
        db.add(FreightPoint(freight_id=freight.id, sequence=1, consignee_id=consignee.id))
        db.add(
            FreightLeg(
                freight_id=freight.id,
                sequence=1,
                vehicle_id=lorries[vtype].id,
                driver_id=driver.id,
                start_odometer=1000,
                end_odometer=1000 + km,
                leg_distance_km=km,
            )
        )
        if vtype == "Dost":
            db.add(
                TripExpense(
                    freight_id=freight.id,
                    type=ExpenseType.TOLL,
                    amount=Decimal("2150"),
                    paid_by=PaidBy.DRIVER,
                    entry_mode=EntryMode.SELF,
                    billable_to_vendor=True,
                    approval_status=ApprovalStatus.APPROVED,
                )
            )

    db.commit()
    data = {"division": str(division.id)}
    db.close()
    return data


def _raise(client, auth, scene):
    res = client.post(
        "/api/invoices",
        json={
            "vendor_division_id": scene["division"],
            "period_from": (TRIP_DAY - timedelta(days=1)).isoformat(),
            "period_to": TODAY.isoformat(),
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
# The tax split
# ---------------------------------------------------------------------------


def test_toll_is_not_taxed(client, scene, auth):
    """Cash handed to a booth and passed on, exactly as their summary has it."""
    invoice = _raise(client, auth, scene)

    # 1,867 + 680 on the Dost, 1,867 on the Ace = 4,414 taxable.
    assert Decimal(invoice["taxable_value"]) == Decimal("4414.00")
    assert Decimal(invoice["zero_rated_value"]) == Decimal("2150.00")


def test_the_tax_is_charged_on_the_taxable_half_only(client, scene, auth):
    """5% of 4,414 is 220.70, split 110.35 each way. Not 5% of 6,564."""
    invoice = _raise(client, auth, scene)

    assert Decimal(invoice["cgst"]) == Decimal("110.35")
    assert Decimal(invoice["sgst"]) == Decimal("110.35")


def test_the_total_still_includes_the_toll(client, scene, auth):
    """Nil-rated is not uncharged. The vendor owes the 2,150 either way."""
    invoice = _raise(client, auth, scene)

    assert Decimal(invoice["total"]) == Decimal("6784.70")  # 4,414 + 2,150 + 220.70


def test_the_rate_is_frozen_onto_the_invoice(client, scene, auth):
    """Read off the division at print time until now, so changing a
    division's rate silently re-rated every invoice raised against it."""
    invoice = _raise(client, auth, scene)
    assert Decimal(invoice["gst_rate_percent"]) == Decimal("5")

    from app.db.session import SessionLocal
    from app.models.vendor import VendorDivision

    db = SessionLocal()
    try:
        db.get(VendorDivision, scene["division"]).gst_rate_percent = Decimal("18")
        db.commit()
    finally:
        db.close()

    again = client.get(f"/api/invoices/{invoice['id']}", headers=auth).json()
    assert Decimal(again["gst_rate_percent"]) == Decimal("5")
    assert Decimal(again["cgst"]) == Decimal("110.35")


def test_the_preview_agrees_with_the_invoice_it_raises(client, scene, auth):
    """A preview that taxes the toll shows a total the invoice then misses."""
    preview = client.post(
        "/api/invoices/preview",
        json={
            "vendor_division_id": scene["division"],
            "period_from": (TRIP_DAY - timedelta(days=1)).isoformat(),
            "period_to": TODAY.isoformat(),
        },
        headers=auth,
    ).json()

    assert Decimal(preview["taxable_value"]) == Decimal("4414.00")
    assert Decimal(preview["zero_rated_value"]) == Decimal("2150.00")
    assert Decimal(preview["total"]) == Decimal("6784.70")


# ---------------------------------------------------------------------------
# The vehicle type, which the freight charge is billed per
# ---------------------------------------------------------------------------


def test_each_line_carries_the_type_it_ran_on(client, scene, auth):
    """Stored, not looked up: a lorry can be re-typed and an invoice must
    reprint as it was issued."""
    invoice = _raise(client, auth, scene)
    detail = client.get(f"/api/invoices/{invoice['id']}", headers=auth).json()

    assert {line["vehicle_type"] for line in detail["lines"]} == {"Dost", "Ace"}


def test_a_retyped_lorry_does_not_change_an_issued_invoice(client, scene, auth):
    invoice = _raise(client, auth, scene)

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.fleet import Vehicle, VehicleType

    db = SessionLocal()
    try:
        ace = db.execute(
            select(VehicleType).where(VehicleType.name == "Ace")
        ).scalars().first()
        dost_lorry = db.execute(
            select(Vehicle).where(Vehicle.registration_no == "KL07CW3317")
        ).scalars().first()
        dost_lorry.vehicle_type_id = ace.id
        db.commit()
    finally:
        db.close()

    detail = client.get(f"/api/invoices/{invoice['id']}", headers=auth).json()
    assert {line["vehicle_type"] for line in detail["lines"]} == {"Dost", "Ace"}
