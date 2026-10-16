"""The unloading charge sheet that goes behind the invoice.

Target Express already hands the vendor a small printed form per delivery:
customer, bill number, how many items, which floor, what was carried, the
amount, a signature. Without it, the unloading line on an invoice is a number
with nothing behind it, and the vendor's accounts team either takes it on
trust or rings somebody.

What these tests hold:

  * THE SHEET AGREES WITH THE INVOICE. The total printed is the stored
    `unloading_billed` — what the vendor was actually charged — not a fresh
    sum. When the working and the charge disagree, the sheet says so rather
    than printing a third number.
  * COOLIE IS NOT UNLOADING. It appears on the sheet, below the total, never
    inside it. A porter demand at a market gate is a reimbursement, and
    folding it in makes "why has unloading gone up?" unanswerable.
  * ONLY THE FREIGHTS ON THE INVOICE. Billing three of a period's five
    freights must not attach the other two vendors' sheets — that is handing
    somebody proof of a charge nobody made.
  * NOTHING UNLOADED, NO SHEET. On a spare-parts run every point would
    otherwise produce a blank form.
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
TRIP_DAY = TODAY - timedelta(days=5)


@pytest.fixture()
def scene(client, auth):
    """One furniture freight, two points: one upstairs, one with nothing carried."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.consignment import Consignment
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint, PointUnloadingItem
    from app.models.rating import RateCard, UnloadingItemRate
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
    # A chair: 50 on the ground, 10 a floor. Carried to the second floor it is
    # 70 each, and two of them are 140.
    db.add(
        UnloadingItemRate(
            vendor_division_id=division.id,
            item_code="CHAIR",
            item_name="Chair",
            base_rate=Decimal("50"),
            per_floor_rate=Decimal("10"),
            driver_base_rate=Decimal("30"),
            driver_per_floor_rate=Decimal("6"),
            effective_from=TRIP_DAY - timedelta(days=30),
            is_active=True,
        )
    )

    owner = VehicleOwner(name="Target Express", phone="9000000041", is_active=True)
    db.add(owner)
    db.flush()
    vehicle = Vehicle(
        owner_id=owner.id, registration_no="KL07CW3317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Suresh", phone="9000000032", is_active=True)
    upstairs = Consignee(
        name="Kottayam Furniture Mart",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Kottayam",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    nothing = Consignee(
        name="Kannur Distribution Centre",
        type=ConsigneeType.DISTRIBUTION_CENTER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([vehicle, driver, upstairs, nothing])
    db.flush()

    freight = Freight(
        trip_no="Y26008001",
        trip_date=TRIP_DAY,
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.COMPLETED,
        point_count=2,
        total_km=100,
        lr_no="801",
    )
    db.add(freight)
    db.flush()

    point = FreightPoint(
        freight_id=freight.id,
        sequence=1,
        consignee_id=upstairs.id,
        address_snapshot="Shop 4, MC Road, Kottayam",
        floor_number=2,
        has_lift=False,
        unloading_billed=Decimal("140.00"),
        coolie_billed=Decimal("120.00"),
        coolie_note="Market gang at the gate",
        receiver_name="Mathew",
    )
    bare = FreightPoint(freight_id=freight.id, sequence=2, consignee_id=nothing.id)
    db.add_all([point, bare])
    db.flush()

    db.add(
        PointUnloadingItem(
            freight_point_id=point.id, item_code="CHAIR", item_name="Chair", quantity=2
        )
    )
    db.add(
        Consignment(
            vendor_division_id=division.id,
            warehouse_id=warehouse.id,
            consignee_id=upstairs.id,
            freight_point_id=point.id,
            vendor_bill_no="GJ/1001",
            bill_date=TRIP_DAY,
        )
    )
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
        "freight": str(freight.id),
        "point": str(point.id),
        "bare_point": str(bare.id),
    }
    db.close()
    return data


# ---------------------------------------------------------------------------
# What is on the sheet
# ---------------------------------------------------------------------------


def test_the_sheet_carries_what_the_dealer_signs_for(client, scene, auth):
    """Customer, bill number, articles, floor and the amount — the paper form."""
    res = client.get(f"/api/freights/{scene['freight']}/unloading-sheets", headers=auth)
    assert res.status_code == 200, res.text

    sheets = res.json()
    assert len(sheets) == 1
    sheet = sheets[0]

    assert sheet["customer_name"] == "Kottayam Furniture Mart"
    assert sheet["location"] == "Shop 4, MC Road, Kottayam"
    assert sheet["vendor_bill_nos"] == ["GJ/1001"]
    assert sheet["trip_no"] == "Y26008001"
    assert sheet["lr_no"] == "801"
    assert sheet["vehicle_no"] == "KL07CW3317"
    assert sheet["receiver_name"] == "Mathew"
    assert sheet["item_count"] == 2
    assert sheet["floor_number"] == 2
    assert sheet["has_lift"] is False


def test_the_climb_is_priced_into_each_article(client, scene, auth):
    """50 on the ground plus two floors at 10 is 70 each, 140 for two."""
    sheet = client.get(
        f"/api/freights/{scene['freight']}/unloading-sheets", headers=auth
    ).json()[0]

    line = sheet["lines"][0]
    assert line["item_name"] == "Chair"
    assert line["quantity"] == 2
    assert Decimal(line["base_rate"]) == Decimal("50.00")
    assert line["floors_charged"] == 2
    assert Decimal(line["unit_charge"]) == Decimal("70.00")
    assert Decimal(line["amount"]) == Decimal("140.00")

    assert Decimal(sheet["rebuilt_total"]) == Decimal("140.00")
    assert Decimal(sheet["billed_total"]) == Decimal("140.00")
    assert sheet["agrees_with_invoice"] is True


def test_coolie_sits_outside_the_unloading_total(client, scene, auth):
    """A porter demand is a reimbursement, not unloading work."""
    sheet = client.get(
        f"/api/freights/{scene['freight']}/unloading-sheets", headers=auth
    ).json()[0]

    assert Decimal(sheet["coolie_billed"]) == Decimal("120.00")
    assert sheet["coolie_note"] == "Market gang at the gate"
    # The 120 is nowhere inside the 140.
    assert Decimal(sheet["billed_total"]) == Decimal("140.00")


def test_a_point_that_unloaded_nothing_has_no_sheet(client, scene, auth):
    """A blank form attached to an invoice is noise."""
    sheets = client.get(
        f"/api/freights/{scene['freight']}/unloading-sheets", headers=auth
    ).json()

    assert [s["point_id"] for s in sheets] == [scene["point"]]
    assert scene["bare_point"] not in [s["point_id"] for s in sheets]


def test_a_corrected_charge_is_flagged_rather_than_hidden(client, scene, auth):
    """The office raised the charge after the driver saved his sheet.

    The printed total has to follow the invoice, and the disagreement has to
    be visible — a sheet that quietly prints a different figure from the bill
    it backs is worse than no sheet.
    """
    from app.db.session import SessionLocal
    from app.models.freight import FreightPoint

    db = SessionLocal()
    try:
        point = db.get(FreightPoint, scene["point"])
        point.unloading_billed = Decimal("200.00")
        db.commit()
    finally:
        db.close()

    sheet = client.get(
        f"/api/freights/{scene['freight']}/unloading-sheets", headers=auth
    ).json()[0]

    assert Decimal(sheet["billed_total"]) == Decimal("200.00")
    assert Decimal(sheet["rebuilt_total"]) == Decimal("140.00")
    assert sheet["agrees_with_invoice"] is False


def test_an_article_with_no_rate_is_surfaced(client, scene, auth):
    """Billed as nothing is money given away, so it belongs on the screen."""
    from app.db.session import SessionLocal
    from app.models.freight import PointUnloadingItem

    db = SessionLocal()
    try:
        db.add(
            PointUnloadingItem(
                freight_point_id=scene["point"],
                item_code="WARDROBE",
                item_name="Wardrobe",
                quantity=1,
            )
        )
        db.commit()
    finally:
        db.close()

    sheet = client.get(
        f"/api/freights/{scene['freight']}/unloading-sheets", headers=auth
    ).json()[0]

    assert sheet["unpriced_item_codes"] == ["WARDROBE"]


def test_the_name_shown_at_the_door_survives_a_rename(client, scene, auth):
    """A rate card is live; what the driver was shown is not."""
    from app.db.session import SessionLocal
    from app.models.rating import UnloadingItemRate

    db = SessionLocal()
    try:
        rate = db.execute(
            __import__("sqlalchemy").select(UnloadingItemRate)
        ).scalars().first()
        rate.item_name = "Chair (stackable)"
        db.commit()
    finally:
        db.close()

    sheet = client.get(
        f"/api/freights/{scene['freight']}/unloading-sheets", headers=auth
    ).json()[0]

    assert sheet["lines"][0]["item_name"] == "Chair"


# ---------------------------------------------------------------------------
# Following the invoice, not the period
# ---------------------------------------------------------------------------


def test_the_sheets_follow_the_invoices_own_lines(client, scene, auth):
    """A freight left off the bill must not have its sheet attached to it."""
    from app.db.session import SessionLocal
    from app.models.enums import FreightStatus
    from app.models.freight import Freight, FreightPoint, PointUnloadingItem

    # A second furniture freight in the same period, deliberately not billed.
    db = SessionLocal()
    try:
        first = db.get(Freight, scene["freight"])
        other = Freight(
            trip_no="Y26008002",
            trip_date=TRIP_DAY,
            vendor_division_id=first.vendor_division_id,
            warehouse_id=first.warehouse_id,
            status=FreightStatus.COMPLETED,
            point_count=1,
            total_km=80,
        )
        db.add(other)
        db.flush()
        point = FreightPoint(
            freight_id=other.id,
            sequence=1,
            consignee_id=first.points[0].consignee_id,
            unloading_billed=Decimal("50.00"),
        )
        db.add(point)
        db.flush()
        db.add(
            PointUnloadingItem(
                freight_point_id=point.id, item_code="CHAIR", item_name="Chair", quantity=1
            )
        )
        db.commit()
    finally:
        db.close()

    created = client.post(
        "/api/invoices",
        json={
            "vendor_division_id": scene["division"],
            "period_from": (TRIP_DAY - timedelta(days=1)).isoformat(),
            "period_to": TODAY.isoformat(),
            "freight_ids": [scene["freight"]],
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    invoice_id = created.json()["id"]

    sheets = client.get(
        f"/api/invoices/{invoice_id}/unloading-sheets", headers=auth
    ).json()
    assert [s["trip_no"] for s in sheets] == ["Y26008001"]


def test_a_selection_can_be_seen_before_the_invoice_exists(client, scene, auth):
    """The office sees what the vendor will be sent while it can still change."""
    res = client.get(
        "/api/unloading-sheets",
        params={"freight_ids": [scene["freight"]]},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert len(res.json()) == 1


def test_an_unknown_invoice_is_a_404_not_an_empty_list(client, auth):
    """An empty list would read as "this invoice has no unloading"."""
    import uuid

    res = client.get(f"/api/invoices/{uuid.uuid4()}/unloading-sheets", headers=auth)
    assert res.status_code == 404
