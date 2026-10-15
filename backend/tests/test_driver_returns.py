"""The driver scanning what came back, at the warehouse, before he closes.

The last thing a trip needs: everything loaded was either delivered or came
back, and until both halves are recorded the difference reads as
"unaccounted" — which should mean a box nobody can find, not one standing in
the godown.

The driver does it because he is the one unloading the vehicle. A carton
counted the next morning has already had a night to be misremembered.

The case these tests care about most is the carton marked DELIVERED that is
physically on the lorry. Quietly flipping it to returned would hide a wrong
delivery record; the scan stops and says so.
"""

from datetime import date, datetime

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
    "freights",
    "freight_points",
    "freight_legs",
    "consignments",
    "boxes",
    "point_unloading_items",
)


@pytest.fixture()
def back_at_base(client):
    """Six cartons went out. Four were delivered, two are on the vehicle."""
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.consignment import Box, Consignment
    from app.models.enums import (
        BoxStatus,
        ConsigneeType,
        FreightStatus,
        GeoConfidence,
        UserRole,
    )
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.user import User
    from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()
    user = User(
        full_name="Rajesh K",
        phone="9000000080",
        role=UserRole.DRIVER,
        hashed_password=hash_password("x"),
        is_active=True,
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
    owner = VehicleOwner(name="Target Express", phone="9000000081", is_active=True)
    db.add(owner)
    db.flush()
    vehicle = Vehicle(
        owner_id=owner.id, registration_no="KL07CW3317", lr_next_number=1, is_active=True
    )
    driver = Driver(name="Rajesh K", phone="9000000080", user_id=user.id, is_active=True)
    consignee = Consignee(
        name="Anand Agencies",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([vehicle, driver, consignee])
    db.flush()

    freight = Freight(
        trip_no="Y26009801",
        trip_date=date.today(),
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.IN_TRANSIT,
        point_count=1,
    )
    db.add(freight)
    db.flush()
    point = FreightPoint(
        freight_id=freight.id, sequence=1, consignee_id=consignee.id, loaded_box_count=6
    )
    db.add(point)
    db.add(
        FreightLeg(
            freight_id=freight.id,
            sequence=1,
            vehicle_id=vehicle.id,
            driver_id=driver.id,
            start_odometer=1000,
            started_at=datetime.now(),
        )
    )
    db.flush()

    consignment = Consignment(
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        consignee_id=consignee.id,
        freight_point_id=point.id,
        vendor_bill_no="GDJ/9801",
        bill_date=date.today(),
        declared_box_count=6,
    )
    db.add(consignment)
    db.flush()
    for n in range(1, 7):
        db.add(
            Box(
                consignment_id=consignment.id,
                item_no=n,
                barcode=f"TE-RB01-{n:03d}",
                item_name="Chair",
                # Four handed over, two still aboard.
                status=BoxStatus.DELIVERED if n <= 4 else BoxStatus.IN_TRANSIT,
            )
        )
    db.commit()

    data = {
        "freight": str(freight.id),
        "headers": {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"},
    }
    db.close()
    return data


def _scan(client, base, code, **extra):
    return client.post(
        f"/api/driver/freights/{base['freight']}/returns",
        json={"code": code, **extra},
        headers=base["headers"],
    )


# ---------------------------------------------------------------------------
# Closing the count
# ---------------------------------------------------------------------------


def test_before_scanning_the_difference_is_unaccounted(client, back_at_base):
    """Which is the problem. Two cartons are standing in the godown and the
    reconciliation calls them missing."""
    body = client.get(
        f"/api/driver/freights/{back_at_base['freight']}/reconciliation",
        headers=back_at_base["headers"],
    ).json()

    assert body["loaded"] == 6
    assert body["delivered"] == 4
    assert body["returned"] == 0
    assert body["unaccounted"] == 2


def test_scanning_a_returned_carton_accounts_for_it(client, back_at_base):
    res = _scan(client, back_at_base, "TE-RB01-005")
    assert res.status_code == 200, res.text

    body = res.json()
    assert body["result"] == "OK"
    assert body["returned"] == 1
    assert body["unaccounted"] == 1


def test_scanning_both_closes_the_count(client, back_at_base):
    """The point: nothing unaccounted, so "missing" can mean missing."""
    _scan(client, back_at_base, "TE-RB01-005")
    body = _scan(client, back_at_base, "TE-RB01-006").json()

    assert body["returned"] == 2
    assert body["unaccounted"] == 0


def test_the_scan_says_which_carton_it_was(client, back_at_base):
    """He is holding it. Naming the bill confirms he scanned what he thinks."""
    body = _scan(client, back_at_base, "TE-RB01-005").json()
    assert body["barcode"] == "TE-RB01-005"
    assert body["bill_no"] == "GDJ/9801"
    assert body["item_name"] == "Chair"


def test_a_reason_can_be_given(client, back_at_base):
    _scan(client, back_at_base, "TE-RB01-005", status="DAMAGED", reason="Leg broken in transit")

    from app.db.session import SessionLocal
    from app.models.consignment import Box
    from sqlalchemy import select

    db = SessionLocal()
    try:
        box = db.execute(
            select(Box).where(Box.barcode == "TE-RB01-005")
        ).scalar_one()
        assert box.status == "DAMAGED"
        assert "Leg broken" in box.return_reason
    finally:
        db.close()


def test_whitespace_and_case_from_a_scanner_are_tolerated(client, back_at_base):
    assert _scan(client, back_at_base, "  te-rb01-005  ").json()["result"] == "OK"


# ---------------------------------------------------------------------------
# The scans that should stop him
# ---------------------------------------------------------------------------


def test_a_carton_marked_delivered_stops_the_scan(client, back_at_base):
    """It is on the lorry and the record says it was handed over. One of those
    is wrong, and quietly flipping the box would hide it."""
    res = _scan(client, back_at_base, "TE-RB01-001")
    assert res.status_code == 200, "a bad scan is never an error dialog"

    body = res.json()
    assert body["result"] == "WAS_DELIVERED"
    assert "Tell the office" in body["message"]
    assert body["returned"] == 0, "it was recorded anyway"


def test_a_sticker_from_another_trip_is_reported(client, back_at_base):
    body = _scan(client, back_at_base, "TE-SOMEONE-ELSE-001").json()
    assert body["result"] == "UNKNOWN"
    assert body["returned"] == 0


def test_scanning_the_same_carton_twice_does_not_double_count(client, back_at_base):
    _scan(client, back_at_base, "TE-RB01-005")
    body = _scan(client, back_at_base, "TE-RB01-005").json()

    assert body["result"] == "ALREADY"
    assert body["returned"] == 1


def test_another_drivers_trip_is_refused(client, back_at_base):
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.fleet import Driver
    from app.models.user import User

    db = SessionLocal()
    other = User(
        full_name="Someone Else",
        phone="9000000082",
        role=UserRole.DRIVER,
        hashed_password=hash_password("x"),
        is_active=True,
    )
    db.add(other)
    db.flush()
    db.add(Driver(name="Someone Else", phone="9000000082", user_id=other.id, is_active=True))
    db.commit()
    token = create_access_token(str(other.id), other.role)
    db.close()

    res = client.post(
        f"/api/driver/freights/{back_at_base['freight']}/returns",
        json={"code": "TE-RB01-005"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_scanning_needs_a_driver_login(client, back_at_base):
    res = client.post(
        f"/api/driver/freights/{back_at_base['freight']}/returns",
        json={"code": "TE-RB01-005"},
    )
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# It reaches the office
# ---------------------------------------------------------------------------


def test_what_he_scans_shows_up_under_returns(client, back_at_base, auth):
    """One list, whoever recorded it. The office should not have to ask the
    driver what came back."""
    _scan(client, back_at_base, "TE-RB01-005", reason="Refused, wrong model")

    rows = client.get("/api/returns", headers=auth).json()
    assert len(rows) == 1
    assert rows[0]["barcode"] == "TE-RB01-005"
    assert rows[0]["reason"] == "Refused, wrong model"
    assert rows[0]["returned_by"] == "Rajesh K"
