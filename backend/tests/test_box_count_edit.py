"""Correcting how many cartons a bill actually has.

The count is typed from the vendor's paperwork at seven in the morning and it
is wrong often enough to matter: the bill says six, five turn up. The only
remedy was to delete the consignment and re-enter it, which also threw away
whatever had been attached, labelled or scanned — so in practice people
printed the labels they had and carried the correction in their heads.

Two things these hold, and the second is the one that makes it safe:

  * CARTONS ARE ADDED AND REMOVED FROM THE END, never regenerated. A barcode
    already printed is on a sticker on a real carton and in a scan log;
    reissuing the lot would orphan both.
  * A CARTON THAT HAS BEEN LOADED OR DELIVERED CANNOT BE REMOVED. It is a
    fact about a real box on a real lorry. A count that disagrees with it is
    the office's to reconcile, not something to make disappear.
"""

from __future__ import annotations

from datetime import date

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
)


@pytest.fixture()
def bill(client, auth):
    """One bill of six cartons, on a stop."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence
    from app.models.freight import Freight, FreightPoint
    from app.models.vendor import Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()
    vendor = Vendor(name="Godrej", is_active=True)
    db.add(vendor)
    db.flush()
    division = VendorDivision(
        vendor_id=vendor.id, name="OCP", code="OCP", invoice_series="191", is_active=True
    )
    warehouse = VendorWarehouse(vendor_id=vendor.id, name="Kochi", code="KOCHI")
    consignee = Consignee(
        name="Rinshad Km",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Aluva",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([division, warehouse, consignee])
    db.flush()

    freight = Freight(
        trip_no="Y26000011",
        trip_date=date.today(),
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.PLANNED,
        point_count=1,
    )
    db.add(freight)
    db.flush()
    point = FreightPoint(freight_id=freight.id, sequence=1, consignee_id=consignee.id)
    db.add(point)
    db.commit()
    ids = {
        "division": str(division.id),
        "warehouse": str(warehouse.id),
        "consignee": str(consignee.id),
        "freight": str(freight.id),
        "point": str(point.id),
    }
    db.close()

    created = client.post(
        "/api/consignments",
        json={
            "vendor_division_id": ids["division"],
            "warehouse_id": ids["warehouse"],
            "consignee_id": ids["consignee"],
            "vendor_bill_no": "GDJ/8870",
            "bill_date": date.today().isoformat(),
            "box_count": 6,
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    ids["consignment"] = created.json()["id"]

    attached = client.post(
        f"/api/freights/{ids['freight']}/points/{ids['point']}/consignments",
        json={"consignment_ids": [ids["consignment"]]},
        headers=auth,
    )
    assert attached.status_code == 204, attached.text
    return ids


def _boxes(client, auth, bill):
    return client.get(
        f"/api/consignments/{bill['consignment']}/boxes", headers=auth
    ).json()


def _set(client, auth, bill, count):
    return client.patch(
        f"/api/consignments/{bill['consignment']}/boxes",
        json={"box_count": count},
        headers=auth,
    )


def _point_count(point_id: str) -> int:
    from app.db.session import SessionLocal
    from app.models.freight import FreightPoint

    db = SessionLocal()
    try:
        return db.get(FreightPoint, point_id).loaded_box_count
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fewer than the bill said
# ---------------------------------------------------------------------------


def test_the_count_can_come_down(client, bill, auth):
    """The bill says six, five turned up."""
    res = _set(client, auth, bill, 5)
    assert res.status_code == 200, res.text
    assert res.json()["declared_box_count"] == 5
    assert len(_boxes(client, auth, bill)) == 5


def test_the_barcodes_already_printed_are_kept(client, bill, auth):
    """They are on stickers on real cartons. Reissuing them would orphan both
    the sticker and the scan log."""
    before = [b["barcode"] for b in _boxes(client, auth, bill)]

    _set(client, auth, bill, 4)

    after = [b["barcode"] for b in _boxes(client, auth, bill)]
    assert after == before[:4]


def test_a_loaded_carton_cannot_be_removed(client, bill, auth):
    """It is on the lorry. A count that disagrees is the office's to
    reconcile, not something to make disappear."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.consignment import Box
    from app.models.enums import BoxStatus

    db = SessionLocal()
    try:
        for box in db.execute(select(Box).order_by(Box.item_no)).scalars().all()[:5]:
            box.status = BoxStatus.LOADED
        db.commit()
    finally:
        db.close()

    res = _set(client, auth, bill, 2)
    assert res.status_code == 409
    assert "already been loaded" in res.json()["detail"]
    assert len(_boxes(client, auth, bill)) == 6


# ---------------------------------------------------------------------------
# More than the bill said
# ---------------------------------------------------------------------------


def test_the_count_can_go_up(client, bill, auth):
    res = _set(client, auth, bill, 8)
    assert res.status_code == 200, res.text

    boxes = _boxes(client, auth, bill)
    assert len(boxes) == 8
    assert [b["item_no"] for b in boxes] == [1, 2, 3, 4, 5, 6, 7, 8]


def test_new_cartons_carry_the_same_article(client, bill, auth):
    """Two more chairs are still chairs, and unloading is priced per article."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.consignment import Box

    db = SessionLocal()
    try:
        for box in db.execute(select(Box)).scalars().all():
            box.item_code = "CHAIR"
            box.item_name = "Chair"
        db.commit()
    finally:
        db.close()

    _set(client, auth, bill, 8)
    assert all(b["item_code"] == "CHAIR" for b in _boxes(client, auth, bill))


# ---------------------------------------------------------------------------
# The stop it is attached to
# ---------------------------------------------------------------------------


def test_the_stops_count_moves_with_it(client, bill, auth):
    """Otherwise the freight screen reports a figure the labels disagree
    with, which is how a sorting sheet stops being trusted."""
    assert _point_count(bill["point"]) == 6

    _set(client, auth, bill, 4)
    assert _point_count(bill["point"]) == 4

    _set(client, auth, bill, 9)
    assert _point_count(bill["point"]) == 9


def test_an_unknown_bill_is_a_404(client, auth):
    import uuid

    res = client.patch(
        f"/api/consignments/{uuid.uuid4()}/boxes", json={"box_count": 3}, headers=auth
    )
    assert res.status_code == 404


def test_zero_is_refused(client, bill, auth):
    """A bill with no cartons is not a correction, it is a deletion."""
    assert _set(client, auth, bill, 0).status_code == 422
