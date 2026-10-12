"""Cartons that came back.

The reconciliation has always counted returns — loaded minus delivered minus
returned is what says whether anything is genuinely missing. With no way to
record one, every carton that came back counted as unaccounted, which is the
alarm that should be reserved for a box nobody can find. These tests care most
about that: recording a return has to take a carton OUT of unaccounted.

The second thing they hold is that a stack of cartons at the godown door is not
rejected wholesale because one sticker was misread.
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
def scene(client, auth):
    """One stop, six cartons, all loaded onto the vehicle."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.consignment import Box, Consignment
    from app.models.enums import (
        BoxStatus,
        ConsigneeType,
        FreightStatus,
        GeoConfidence,
    )
    from app.models.freight import Freight, FreightPoint
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
        is_active=True,
    )
    warehouse = VendorWarehouse(vendor_id=vendor.id, name="Kochi godown", code="KOCHI")
    db.add_all([division, warehouse])
    db.flush()
    consignee = Consignee(
        name="Anand Agencies",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add(consignee)
    db.flush()

    freight = Freight(
        trip_no="Y26007701",
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
    db.flush()

    consignment = Consignment(
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        consignee_id=consignee.id,
        freight_point_id=point.id,
        vendor_bill_no="GDJ/7701",
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
                barcode=f"TE-RET01-{n:03d}",
                item_name="Chair",
                item_code="CHAIR",
                status=BoxStatus.LOADED,
            )
        )
    db.commit()
    data = {"freight": str(freight.id), "point": str(point.id)}
    db.close()
    return data


def _record(client, auth, barcodes, status="RETURNED_TO_WAREHOUSE", reason="Refused, wrong model"):
    return client.post(
        "/api/returns",
        json={"barcodes": barcodes, "status": status, "reason": reason},
        headers=auth,
    )


# ---------------------------------------------------------------------------
# Recording one
# ---------------------------------------------------------------------------


def test_cartons_can_be_recorded_as_returned(client, scene, auth):
    res = _record(client, auth, ["TE-RET01-001", "TE-RET01-002"])
    assert res.status_code == 201, res.text

    body = res.json()
    assert len(body["recorded"]) == 2
    assert body["unknown"] == []


def test_the_reason_is_kept(client, scene, auth):
    """"12 boxes came back" is a number. "4 refused, wrong model" is something
    the vendor can be told and the warehouse can act on."""
    _record(client, auth, ["TE-RET01-001"], reason="Refused — wrong model sent")

    row = client.get("/api/returns", headers=auth).json()[0]
    assert row["reason"] == "Refused — wrong model sent"


def test_the_return_says_who_recorded_it(client, scene, auth):
    _record(client, auth, ["TE-RET01-001"])
    row = client.get("/api/returns", headers=auth).json()[0]
    assert row["returned_by"] == "Test Admin"
    assert row["returned_at"]


def test_the_return_carries_its_context(client, scene, auth):
    """The vendor's first question is which bill and which customer."""
    _record(client, auth, ["TE-RET01-003"])
    row = client.get("/api/returns", headers=auth).json()[0]

    assert row["vendor_bill_no"] == "GDJ/7701"
    assert row["consignee_name"] == "Anand Agencies"
    assert row["trip_no"] == "Y26007701"
    assert row["item_name"] == "Chair"


def test_only_the_named_cartons_come_back(client, scene, auth):
    """Three of six, not all or nothing — which is how they actually return."""
    _record(client, auth, ["TE-RET01-001", "TE-RET01-002", "TE-RET01-003"])
    assert len(client.get("/api/returns", headers=auth).json()) == 3


def test_damaged_is_recorded_separately_from_refused(client, scene, auth):
    _record(client, auth, ["TE-RET01-001"], status="DAMAGED", reason="Leg broken in transit")
    _record(client, auth, ["TE-RET01-002"], reason="Refused")

    summary = client.get("/api/returns/summary", headers=auth).json()
    assert summary["damaged"] == 1
    assert summary["returned_to_warehouse"] == 1
    assert summary["total"] == 2


# ---------------------------------------------------------------------------
# The reconciliation, which is the point
# ---------------------------------------------------------------------------


def test_a_recorded_return_is_no_longer_unaccounted(client, scene, auth):
    """The whole reason this exists. Before, a carton that came back counted as
    missing — and "missing" should mean nobody can find it."""
    from app.db.session import SessionLocal
    from app.services.controls import reconcile_boxes

    _record(client, auth, ["TE-RET01-001", "TE-RET01-002"])

    db = SessionLocal()
    try:
        result = reconcile_boxes(db, scene["freight"])
    finally:
        db.close()

    assert result.returned == 2
    assert result.unaccounted == 4, "the other four are still out, not missing"


# ---------------------------------------------------------------------------
# Slips at the godown door
# ---------------------------------------------------------------------------


def test_an_unknown_sticker_does_not_reject_the_rest(client, scene, auth):
    """A stack of cartons is not refused wholesale because one was misread."""
    res = _record(client, auth, ["TE-RET01-001", "SOME-OTHER-COURIER-99"])
    assert res.status_code == 201

    body = res.json()
    assert len(body["recorded"]) == 1
    assert body["unknown"] == ["SOME-OTHER-COURIER-99"]


def test_recording_the_same_carton_twice_does_not_rewrite_it(client, scene, auth):
    """It would move the reason and the timestamp, quietly changing who said
    what and when."""
    _record(client, auth, ["TE-RET01-001"], reason="Refused, wrong model")
    res = _record(client, auth, ["TE-RET01-001"], reason="Something else entirely")

    assert res.json()["already"] == ["TE-RET01-001"]
    assert client.get("/api/returns", headers=auth).json()[0]["reason"] == "Refused, wrong model"


def test_whitespace_and_case_from_a_scanner_are_tolerated(client, scene, auth):
    res = _record(client, auth, ["  te-ret01-001  "])
    assert len(res.json()["recorded"]) == 1


def test_a_reason_is_required(client, scene, auth):
    """A return with no reason is an unexplained hole in the reconciliation."""
    res = client.post(
        "/api/returns",
        json={"barcodes": ["TE-RET01-001"], "status": "DAMAGED", "reason": ""},
        headers=auth,
    )
    assert res.status_code == 422


def test_delivered_is_not_a_return(client, scene, auth):
    res = _record(client, auth, ["TE-RET01-001"], status="DELIVERED", reason="Handed over")
    assert res.status_code == 422
    assert "not a return" in res.json()["detail"]


def test_recording_a_return_needs_a_login(client, scene):
    res = client.post(
        "/api/returns",
        json={"barcodes": ["TE-RET01-001"], "reason": "Refused"},
    )
    assert res.status_code == 401
