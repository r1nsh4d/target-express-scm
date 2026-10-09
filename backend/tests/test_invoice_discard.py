"""Throwing away an invoice raised by mistake.

Generating an invoice is one button and it sweeps up every completed freight in
the period. Pick the wrong division, or a period a week too wide, and before
this the mistake was permanent: the freights were already BILLED, which is the
one status an admin may not set by hand, so they could neither be put back nor
invoiced again.

The thing these tests actually guard is the release. An invoice that deletes
without handing its freights back is worse than no delete at all — the work
would be stuck BILLED against a document that no longer exists, and would never
appear on another invoice. That is unbilled revenue, silently.
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


@pytest.fixture()
def billed(client, auth):
    """One priced, completed freight, invoiced into a draft."""
    from app.db.session import SessionLocal
    from app.models.billing import VendorInvoice
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.rating import RateCard
    from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse
    from app.services.invoicing import create_invoice

    db = SessionLocal()
    trip_day = date.today() - timedelta(days=3)

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
        gst_rate_percent=Decimal("12"),
        is_active=True,
    )
    warehouse = VendorWarehouse(vendor_id=vendor.id, name="Kochi godown", code="KOCHI")
    db.add_all([division, warehouse])
    db.flush()

    # The verified Godrej card: 1,867 covering 60 km and 3 points.
    db.add(
        RateCard(
            vendor_division_id=division.id,
            base_trip_amount=Decimal("1867"),
            included_km=60,
            included_points=3,
            extra_km_rate=Decimal("17"),
            extra_point_rate=Decimal("175"),
            effective_from=trip_day - timedelta(days=30),
            is_active=True,
        )
    )

    owner = VehicleOwner(name="Target Express", phone="9000000040", is_active=True)
    db.add(owner)
    db.flush()
    vehicle = Vehicle(
        owner_id=owner.id, registration_no="KL07CW3317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Suresh", phone="9000000031", is_active=True)
    consignee = Consignee(
        name="Kannur Distribution Centre",
        type=ConsigneeType.DISTRIBUTION_CENTER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([vehicle, driver, consignee])
    db.flush()

    freight = Freight(
        trip_no="Y26009001",
        trip_date=trip_day,
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.COMPLETED,
        point_count=1,
        total_km=120,
        lr_no="774",
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
            end_odometer=1120,
            leg_distance_km=120,
        )
    )
    db.commit()

    invoice = create_invoice(
        db, division, trip_day - timedelta(days=1), date.today(), date.today(), issued_by_id=None
    )
    db.commit()

    data = {
        "invoice": str(invoice.id),
        "invoice_no": invoice.invoice_no,
        "freight": str(freight.id),
        "division": str(division.id),
        "period_from": (trip_day - timedelta(days=1)).isoformat(),
        "period_to": date.today().isoformat(),
    }
    db.close()
    return data


def _freight_status(freight_id: str) -> str:
    from app.db.session import SessionLocal
    from app.models.freight import Freight

    db = SessionLocal()
    try:
        return db.get(Freight, freight_id).status
    finally:
        db.close()


# ---------------------------------------------------------------------------
# What generating did
# ---------------------------------------------------------------------------


def test_generating_marks_the_freight_billed(client, billed, auth):
    """The starting point: this is how a freight reaches BILLED at all."""
    assert _freight_status(billed["freight"]) == "BILLED"


# ---------------------------------------------------------------------------
# Discarding a draft
# ---------------------------------------------------------------------------


def test_a_draft_can_be_discarded(client, billed, auth):
    res = client.delete(f"/api/invoices/{billed['invoice']}", headers=auth)
    assert res.status_code == 204, res.text

    rows = client.get("/api/invoices", headers=auth).json()
    assert all(r["id"] != billed["invoice"] for r in rows)


def test_discarding_gives_the_freight_back(client, billed, auth):
    """The whole point. A freight left BILLED against an invoice that no longer
    exists would never appear on another one — unbilled revenue, silently."""
    client.delete(f"/api/invoices/{billed['invoice']}", headers=auth)
    assert _freight_status(billed["freight"]) == "COMPLETED"


def test_the_freight_can_then_be_invoiced_again(client, billed, auth):
    """Proof the release is real and not cosmetic: the next run picks the
    freight up again."""
    client.delete(f"/api/invoices/{billed['invoice']}", headers=auth)

    res = client.post(
        "/api/invoices",
        json={
            "vendor_division_id": billed["division"],
            "period_from": billed["period_from"],
            "period_to": billed["period_to"],
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text
    assert res.json()["line_count"] == 1


def test_the_lines_go_with_it(client, billed, auth):
    from app.db.session import SessionLocal
    from app.models.billing import VendorInvoiceLine
    from sqlalchemy import func, select

    client.delete(f"/api/invoices/{billed['invoice']}", headers=auth)

    db = SessionLocal()
    try:
        left = db.execute(select(func.count()).select_from(VendorInvoiceLine)).scalar()
    finally:
        db.close()
    assert left == 0, "invoice lines outlived the invoice"


# ---------------------------------------------------------------------------
# What may not be discarded
# ---------------------------------------------------------------------------


def test_an_issued_invoice_is_not_deletable(client, billed, auth):
    """It has a number the vendor has seen. Deleting it would leave a hole in
    the series, which is the first thing an auditor looks for."""
    client.patch(
        f"/api/invoices/{billed['invoice']}", json={"status": "ISSUED"}, headers=auth
    )

    res = client.delete(f"/api/invoices/{billed['invoice']}", headers=auth)
    assert res.status_code == 409
    assert "series" in res.json()["detail"]


def test_a_refused_delete_leaves_the_freight_billed(client, billed, auth):
    """A rejected delete must not half-apply."""
    client.patch(
        f"/api/invoices/{billed['invoice']}", json={"status": "ISSUED"}, headers=auth
    )
    client.delete(f"/api/invoices/{billed['invoice']}", headers=auth)

    assert _freight_status(billed["freight"]) == "BILLED"
    assert client.get(f"/api/invoices/{billed['invoice']}", headers=auth).status_code == 200


def test_an_unknown_invoice_is_404(client, billed, auth):
    res = client.delete(
        "/api/invoices/00000000-0000-0000-0000-000000000000", headers=auth
    )
    assert res.status_code == 404


def test_discarding_needs_a_login(client, billed):
    assert client.delete(f"/api/invoices/{billed['invoice']}").status_code == 401
