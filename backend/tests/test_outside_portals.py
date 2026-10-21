"""Logins that belong to somebody outside Target Express.

A vendor raises its own runs, reads what it agreed and reconciles its bills.
A vehicle owner sees what his lorries earned and what he has drawn. Both are
people we do business with rather than people we employ, and that changes
what a bug costs: an office screen that shows too much is untidy, and one of
these that shows too much hands a competitor's figures to a competitor.

SO THE SCOPING IS WHAT IS TESTED HARDEST. Not "does the list render" but
"does Godrej's login return a single row of Usha's", asked of every endpoint,
including the ones where the id is supplied by the caller.

The other rule each portal has:

  A VENDOR CANNOT DISPATCH. They raise a DRAFT because they know what is
  going out before we do; the lorry, the labels and the dispatch are ours.
  A vendor pressing dispatch would be a vendor telling us a lorry has left.

  AN OWNER NEVER SEES WHAT THE VENDOR WAS CHARGED. The gap between what
  Godrej pays and what he is paid is Target Express's margin, and handing a
  contractor both halves of it is handing him a negotiation.
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
)

TODAY = date.today()
TRIP_DAY = TODAY - timedelta(days=2)


def _login(role: str, phone: str, **ties):
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.user import User

    db = SessionLocal()
    try:
        user = User(
            full_name=role.title(),
            phone=phone,
            role=UserRole[role],
            hashed_password=hash_password("x"),
            is_active=True,
            **ties,
        )
        db.add(user)
        db.commit()
        return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}
    finally:
        db.close()


@pytest.fixture()
def world(client, auth):
    """Two vendors, two owners, and a run for each — so scoping can be tested.

    Godrej and Usha are competitors. Each has a division, a warehouse, a rate
    card and a completed freight. One lorry is Target Express's own, one is
    rented from Shaji and one from Basheer.
    """
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
        VehicleOwnership,
    )
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.rating import RateCard, UnloadingItemRate
    from app.models.settlement import Advance, FreightPayout
    from app.models.vendor import Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()
    data: dict = {}

    driver = Driver(name="Suresh", phone="9000000601", is_active=True)
    db.add(driver)
    db.flush()

    for key, vendor_name, owner_name, reg, phone in (
        ("godrej", "Godrej", "Shaji", "KL07CW3317", "9000000611"),
        ("usha", "Usha", "Basheer", "KL41U0317", "9000000612"),
    ):
        vendor = Vendor(name=vendor_name, payment_terms_days=30, is_active=True)
        owner = VehicleOwner(name=owner_name, phone=phone, is_active=True)
        db.add_all([vendor, owner])
        db.flush()

        division = VendorDivision(
            vendor_id=vendor.id,
            name=f"{vendor_name} Main",
            code=f"{vendor_name.upper()}-MAIN",
            invoice_series="191",
            gst_rate_percent=Decimal("5"),
            is_active=True,
        )
        warehouse = VendorWarehouse(
            vendor_id=vendor.id, name=f"{vendor_name} godown", code=f"{vendor_name[:3].upper()}"
        )
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

        lorry = Vehicle(
            owner_id=owner.id,
            registration_no=reg,
            ownership=VehicleOwnership.HIRED,
            lr_next_number=1,
            is_active=True,
        )
        consignee = Consignee(
            name=f"{vendor_name} Dealer",
            type=ConsigneeType.RETAIL_CUSTOMER,
            city="Aluva",
            geo_confidence=GeoConfidence.UNVERIFIED,
        )
        db.add_all([lorry, consignee])
        db.flush()

        freight = Freight(
            trip_no=f"Y2602{key[:2].upper()}1",
            trip_date=TRIP_DAY,
            vendor_division_id=division.id,
            warehouse_id=warehouse.id,
            status=FreightStatus.COMPLETED,
            point_count=1,
            total_km=100,
            destination_text="Aluva",
        )
        db.add(freight)
        db.flush()
        point = FreightPoint(
            freight_id=freight.id,
            sequence=1,
            consignee_id=consignee.id,
            delivered_box_count=4,
            loaded_box_count=4,
            receiver_name="Mathew",
            delivery_photo_url=f"https://files/{key}-delivery.jpg",
            customer_rating=5,
            customer_remarks="Carried it up without being asked",
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

        db.add(
            FreightPayout(
                freight_id=freight.id,
                leg_id=leg.id,
                head=ChargeHead.TRANSPORTATION,
                payee_type=PayeeType.VEHICLE_OWNER,
                driver_id=driver.id,
                vehicle_owner_id=owner.id,
                vehicle_id=lorry.id,
                amount=Decimal("1300"),
            )
        )
        db.add(
            Advance(
                payee_type=PayeeType.VEHICLE_OWNER,
                vehicle_owner_id=owner.id,
                advance_date=TRIP_DAY,
                amount=Decimal("500"),
                recovered_amount=Decimal("100"),
                reason="Diesel",
            )
        )

        invoice = VendorInvoice(
            invoice_no=f"191/2026-27/{key[:1].upper()}1",
            invoice_date=TODAY,
            period_from=TRIP_DAY,
            period_to=TODAY,
            vendor_division_id=division.id,
            taxable_value=Decimal("2547"),
            gst_rate_percent=Decimal("5"),
            cgst=Decimal("63.68"),
            sgst=Decimal("63.67"),
            total=Decimal("2674.35"),
            status=InvoiceStatus.ISSUED,
        )
        db.add(invoice)
        db.flush()
        db.add(
            VendorInvoiceLine(
                invoice_id=invoice.id,
                freight_id=freight.id,
                sl_no=1,
                trip_date=TRIP_DAY,
                trip_no=freight.trip_no,
                vehicle_no=reg,
                destination_text="Aluva",
                point_count=1,
                km=100,
                line_total=Decimal("2547"),
            )
        )

        data[key] = {
            "vendor": str(vendor.id),
            "division": str(division.id),
            "warehouse": str(warehouse.id),
            "owner": str(owner.id),
            "freight": str(freight.id),
            "consignee": str(consignee.id),
            "trip_no": freight.trip_no,
        }

    db.commit()
    db.close()
    return data


@pytest.fixture()
def godrej(client, world):
    return _login("VENDOR", "9000000701", vendor_id=world["godrej"]["vendor"])


@pytest.fixture()
def shaji(client, world):
    return _login("VEHICLE_OWNER", "9000000702", vehicle_owner_id=world["godrej"]["owner"])


# ===========================================================================
# The vendor portal
# ===========================================================================


def test_a_vendor_sees_only_its_own_freights(client, world, godrej):
    rows = client.get("/api/vendor/freights", headers=godrej).json()

    assert [r["trip_no"] for r in rows] == [world["godrej"]["trip_no"]]
    assert world["usha"]["trip_no"] not in [r["trip_no"] for r in rows]


def test_another_vendors_freight_is_not_found_rather_than_refused(
    client, world, godrej
):
    """403 would confirm the trip exists, which is itself something a
    competitor should not learn from us."""
    res = client.get(f"/api/vendor/freights/{world['usha']['freight']}", headers=godrej)
    assert res.status_code == 404


def test_a_vendor_sees_only_its_own_rates(client, world, godrej):
    rows = client.get("/api/vendor/rate-cards", headers=godrej).json()

    assert len(rows) == 1
    assert rows[0]["division_name"] == "Godrej Main"


def test_a_vendor_sees_only_its_own_invoices(client, world, godrej):
    rows = client.get("/api/vendor/invoices", headers=godrej).json()

    assert len(rows) == 1
    assert rows[0]["invoice_no"].endswith("G1")


def test_a_draft_invoice_is_not_shown_to_the_vendor(client, world, godrej, auth):
    """A draft is a working copy nobody has sent. A vendor seeing a number
    that may still change is how an argument starts over a figure nobody
    meant."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.billing import VendorInvoice
    from app.models.enums import InvoiceStatus

    db = SessionLocal()
    try:
        for invoice in db.execute(select(VendorInvoice)).scalars().all():
            invoice.status = InvoiceStatus.DRAFT
        db.commit()
    finally:
        db.close()

    assert client.get("/api/vendor/invoices", headers=godrej).json() == []


def test_the_vendor_sees_the_evidence_from_every_door(client, world, godrej):
    """The photographs and what the customer said are the whole reason a
    vendor stops ringing to ask whether something arrived."""
    freight = client.get(
        f"/api/vendor/freights/{world['godrej']['freight']}", headers=godrej
    ).json()

    point = freight["points"][0]
    assert point["delivery_photo_url"].endswith("godrej-delivery.jpg")
    assert point["receiver_name"] == "Mathew"
    assert point["customer_rating"] == 5
    assert "without being asked" in point["customer_remarks"]


def test_a_vendor_can_raise_its_own_run(client, world, godrej):
    """They know what is going out tomorrow before we do."""
    res = client.post(
        "/api/vendor/freights",
        json={
            "vendor_division_id": world["godrej"]["division"],
            "warehouse_id": world["godrej"]["warehouse"],
            "trip_date": TODAY.isoformat(),
            "points": [
                {
                    "consignee_id": world["godrej"]["consignee"],
                    "floor_number": 2,
                    "bill_no": "GDJ/9001",
                    "box_count": 4,
                }
            ],
        },
        headers=godrej,
    )
    assert res.status_code == 201, res.text

    created = res.json()
    # A DRAFT. The lorry, the labels and the dispatch are Target Express's.
    assert created["status"] == "DRAFT"
    assert created["box_count"] == 4
    assert created["vehicle_no"] is None


def test_a_vendor_cannot_raise_a_run_against_somebody_elses_division(
    client, world, godrej
):
    res = client.post(
        "/api/vendor/freights",
        json={
            "vendor_division_id": world["usha"]["division"],
            "warehouse_id": world["usha"]["warehouse"],
            "trip_date": TODAY.isoformat(),
            "points": [{"new_customer_name": "Somebody", "box_count": 0}],
        },
        headers=godrej,
    )
    assert res.status_code == 404


def test_a_vendor_cannot_dispatch(client, world, godrej):
    """That would be a vendor telling us a lorry has left."""
    res = client.post(
        f"/api/freights/{world['godrej']['freight']}/dispatch", headers=godrej
    )
    assert res.status_code == 403


def test_a_vendor_cannot_touch_the_rate_it_reads(client, world, godrej):
    """A rate is an agreement between two companies. One of them editing it
    alone is a dispute discovered at invoice time."""
    res = client.post(
        "/api/rate-cards",
        json={
            "vendor_division_id": world["godrej"]["division"],
            "base_trip_amount": "9999",
            "effective_from": TODAY.isoformat(),
        },
        headers=godrej,
    )
    assert res.status_code == 403


def test_a_vendor_reaches_none_of_the_office(client, world, godrej):
    for path in (
        "/api/freights",
        "/api/invoices",
        "/api/reports",
        "/api/consignees",
        "/api/drivers",
        "/api/settlements",
    ):
        assert client.get(path, headers=godrej).status_code == 403, path


def test_a_vendor_login_with_no_vendor_on_it_is_refused(client, world):
    """A login made wrong is not a login that sees everything."""
    headers = _login("VENDOR", "9000000703")
    res = client.get("/api/vendor/freights", headers=headers)

    assert res.status_code == 403
    assert "not linked to a vendor" in res.json()["detail"]


def test_the_vendors_home_counts_only_its_own(client, world, godrej):
    home = client.get("/api/vendor/home", headers=godrej).json()

    assert home["vendor_name"] == "Godrej"
    assert [d["name"] for d in home["divisions"]] == ["Godrej Main"]
    assert Decimal(home["outstanding"]) == Decimal("2674.35")


# ===========================================================================
# The vehicle owner portal
# ===========================================================================


def test_an_owner_sees_what_his_lorry_earned(client, world, shaji):
    runs = client.get("/api/owner/runs", headers=shaji).json()

    assert len(runs) == 1
    assert runs[0]["trip_no"] == world["godrej"]["trip_no"]
    assert Decimal(runs[0]["earned"]) == Decimal("1300.00")
    assert runs[0]["km"] == 100


def test_an_owner_sees_only_his_own_lorries(client, world, shaji):
    home = client.get("/api/owner/home", headers=shaji).json()

    assert home["owner_name"] == "Shaji"
    assert [v["registration_no"] for v in home["vehicles"]] == ["KL07CW3317"]


def test_an_owner_is_never_shown_what_the_vendor_was_charged(client, world, shaji):
    """The gap between the two is Target Express's margin, and handing a
    contractor both halves of it is handing him a negotiation."""
    body = client.get("/api/owner/runs", headers=shaji).text
    home = client.get("/api/owner/home", headers=shaji).text

    # 2,547 is what Godrej was billed for that same run.
    assert "2547" not in body and "2547" not in home
    assert "1867" not in body and "1867" not in home


def test_an_owner_sees_his_advances_and_what_is_left(client, world, shaji):
    """The commonest dispute with an office is whether an advance was
    recovered twice. Both sides reading one ledger is most of the answer."""
    rows = client.get("/api/owner/advances", headers=shaji).json()

    assert len(rows) == 1
    assert Decimal(rows[0]["amount"]) == Decimal("500.00")
    assert Decimal(rows[0]["outstanding"]) == Decimal("400.00")


def test_an_owner_sees_none_of_another_owners_money(client, world):
    basheer = _login("VEHICLE_OWNER", "9000000704", vehicle_owner_id=world["usha"]["owner"])

    runs = client.get("/api/owner/runs", headers=basheer).json()
    assert [r["trip_no"] for r in runs] == [world["usha"]["trip_no"]]

    advances = client.get("/api/owner/advances", headers=basheer).json()
    assert len(advances) == 1


def test_an_owner_reaches_none_of_the_office(client, world, shaji):
    for path in ("/api/freights", "/api/reports", "/api/settlements", "/api/advances"):
        assert client.get(path, headers=shaji).status_code == 403, path


def test_an_owner_reaches_none_of_the_vendor_portal(client, world, shaji):
    assert client.get("/api/vendor/freights", headers=shaji).status_code == 403


def test_a_vendor_reaches_none_of_the_owner_portal(client, world, godrej):
    assert client.get("/api/owner/runs", headers=godrej).status_code == 403


def test_an_owner_login_with_no_owner_on_it_is_refused(client, world):
    headers = _login("VEHICLE_OWNER", "9000000705")
    res = client.get("/api/owner/runs", headers=headers)

    assert res.status_code == 403
    assert "not linked to a vehicle owner" in res.json()["detail"]


def test_what_is_unsettled_is_what_he_is_ringing_about(client, world, shaji):
    home = client.get("/api/owner/home", headers=shaji).json()

    assert Decimal(home["unsettled"]) == Decimal("1300.00")
    assert Decimal(home["advances_outstanding"]) == Decimal("400.00")
