"""Scanning cartons off the vehicle at a delivery point.

The reason this feature exists is not the count — a driver could type that. It
is that a carton scanned at a stop either belongs there or it does not, and the
phone says so while the customer is still standing in front of him.

A wrong box caught at the door is a thirty-second conversation. The same box
found at the depot that night is a missing delivery, an angry vendor, and a
credit note. So WRONG_POINT is the case these tests care about most.

The second rule they hold: a bad scan is never an error. A driver holding a
carton in one hand gets a verdict on screen, not an exception — every outcome
returns 200 with a result the phone can colour.
"""

from datetime import date

import pytest

pytestmark = pytest.mark.tables(
    "users",
    "goods_categories",
    "vendors",
    "vendor_divisions",
    "vendor_warehouses",
    "consignees",
    "freights",
    "freight_points",
    "consignments",
    "boxes",
)


@pytest.fixture()
def scene(client):
    """Two stops on one freight, three cartons each. The simplest shape that
    can get a box to the wrong door."""
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.consignment import Box, Consignment
    from app.models.enums import (
        ConsigneeType,
        FreightStatus,
        GeoConfidence,
        UserRole,
    )
    from app.models.freight import Freight, FreightPoint
    from app.models.user import User
    from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()

    driver_user = User(
        full_name="Rajesh K",
        phone="9000000010",
        role=UserRole.DRIVER,
        hashed_password=hash_password("x"),
        is_active=True,
    )
    db.add(driver_user)

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

    anand = Consignee(
        name="Anand Agencies",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Kasaragod",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    beena = Consignee(
        name="Beena Stores",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([anand, beena])
    db.flush()

    freight = Freight(
        trip_no="Y26000001",
        trip_date=date.today(),
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.DISPATCHED,
        point_count=2,
    )
    db.add(freight)
    db.flush()

    points = []
    for seq, consignee in ((1, anand), (2, beena)):
        point = FreightPoint(
            freight_id=freight.id,
            sequence=seq,
            consignee_id=consignee.id,
            loaded_box_count=3,
        )
        db.add(point)
        db.flush()
        points.append(point)

        consignment = Consignment(
            vendor_division_id=division.id,
            warehouse_id=warehouse.id,
            consignee_id=consignee.id,
            freight_point_id=point.id,
            vendor_bill_no=f"BILL-{seq}",
            bill_date=date.today(),
        )
        db.add(consignment)
        db.flush()

        for n in range(1, 4):
            db.add(
                Box(
                    consignment_id=consignment.id,
                    item_no=n,
                    barcode=f"TE-STOP{seq}-{n:03d}",
                    item_name=f"Chair {n}",
                )
            )

    db.commit()

    data = {
        "token": create_access_token(str(driver_user.id), driver_user.role),
        "point_1": str(points[0].id),
        "point_2": str(points[1].id),
    }
    db.close()
    return data


@pytest.fixture()
def driver(scene) -> dict[str, str]:
    return {"Authorization": f"Bearer {scene['token']}"}


def _scan(client, headers, point_id: str, code: str):
    return client.post(f"/api/driver/points/{point_id}/scan", json={"code": code}, headers=headers)


# ---------------------------------------------------------------------------
# The good path
# ---------------------------------------------------------------------------


def test_a_box_that_belongs_here_is_confirmed(client, scene, driver):
    res = _scan(client, driver, scene["point_1"], "TE-STOP1-001")
    assert res.status_code == 200, res.text

    body = res.json()
    assert body["result"] == "OK"
    assert body["scanned_count"] == 1
    assert body["expected_count"] == 3
    assert body["all_scanned"] is False


def test_scanning_every_box_completes_the_stop(client, scene, driver):
    for n in (1, 2, 3):
        body = _scan(client, driver, scene["point_1"], f"TE-STOP1-{n:03d}").json()
        assert body["result"] == "OK"

    assert body["scanned_count"] == 3
    assert body["all_scanned"] is True


def test_the_count_is_per_stop_not_per_freight(client, scene, driver):
    """Stop two starts at zero even after stop one is finished."""
    for n in (1, 2, 3):
        _scan(client, driver, scene["point_1"], f"TE-STOP1-{n:03d}")

    body = _scan(client, driver, scene["point_2"], "TE-STOP2-001").json()
    assert body["scanned_count"] == 1
    assert body["expected_count"] == 3


# ---------------------------------------------------------------------------
# The case the feature exists for
# ---------------------------------------------------------------------------


def test_a_box_for_another_stop_is_refused(client, scene, driver):
    """Caught at the door, in front of the customer, before it is handed over."""
    res = _scan(client, driver, scene["point_1"], "TE-STOP2-001")
    assert res.status_code == 200, "a bad scan must not be an error dialog"

    body = res.json()
    assert body["result"] == "WRONG_POINT"
    assert "NOT for this customer" in body["message"]


def test_a_wrong_box_says_where_it_actually_goes(client, scene, driver):
    """So the driver puts it back in the right place rather than guessing."""
    body = _scan(client, driver, scene["point_1"], "TE-STOP2-002").json()

    assert body["belongs_to_point"] == 2
    assert body["belongs_to_consignee"] == "Beena Stores"
    assert body["barcode"] == "TE-STOP2-002"


def test_a_wrong_scan_does_not_count_towards_this_stop(client, scene, driver):
    _scan(client, driver, scene["point_1"], "TE-STOP2-001")
    body = _scan(client, driver, scene["point_1"], "TE-STOP2-002").json()
    assert body["scanned_count"] == 0


def test_a_wrong_scan_does_not_mark_the_other_stop_delivered(client, scene, driver):
    """Scanning Beena's box at Anand's door must not quietly tick it off at
    Beena's."""
    _scan(client, driver, scene["point_1"], "TE-STOP2-001")

    boxes = client.get(
        f"/api/driver/points/{scene['point_2']}/boxes", headers=driver
    ).json()
    assert all(b["scanned"] is False for b in boxes)


# ---------------------------------------------------------------------------
# Slips
# ---------------------------------------------------------------------------


def test_scanning_the_same_box_twice_does_not_double_count(client, scene, driver):
    _scan(client, driver, scene["point_1"], "TE-STOP1-001")
    body = _scan(client, driver, scene["point_1"], "TE-STOP1-001").json()

    assert body["result"] == "ALREADY"
    assert body["scanned_count"] == 1


def test_an_unknown_sticker_is_reported_not_crashed(client, scene, driver):
    body = _scan(client, driver, scene["point_1"], "SOME-OTHER-COURIER-9988").json()
    assert body["result"] == "UNKNOWN"
    assert body["scanned_count"] == 0


def test_whitespace_and_case_from_the_scanner_are_tolerated(client, scene, driver):
    """A camera sometimes returns trailing whitespace, and a person typing the
    code off the sticker will not match our casing."""
    body = _scan(client, driver, scene["point_1"], "  te-stop1-001  ").json()
    assert body["result"] == "OK"


# ---------------------------------------------------------------------------
# The list behind the scanner
# ---------------------------------------------------------------------------


def test_the_box_list_shows_what_should_come_off_here(client, scene, driver):
    rows = client.get(f"/api/driver/points/{scene['point_1']}/boxes", headers=driver).json()

    assert len(rows) == 3
    assert {r["barcode"] for r in rows} == {
        "TE-STOP1-001",
        "TE-STOP1-002",
        "TE-STOP1-003",
    }
    assert all(r["scanned"] is False for r in rows)


def test_the_list_marks_what_has_been_scanned(client, scene, driver):
    """A driver whose camera will not focus in the dark still needs to tick
    them off by eye."""
    _scan(client, driver, scene["point_1"], "TE-STOP1-002")

    rows = client.get(f"/api/driver/points/{scene['point_1']}/boxes", headers=driver).json()
    done = [r for r in rows if r["scanned"]]
    assert len(done) == 1
    assert done[0]["barcode"] == "TE-STOP1-002"


def test_the_list_needs_a_driver_login(client, scene):
    assert client.get(f"/api/driver/points/{scene['point_1']}/boxes").status_code == 401
