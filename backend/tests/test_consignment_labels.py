"""Reprinting the stickers for one vendor bill.

The freight-wide print exists for the morning the lorry is loaded. This one
exists for the two cases that follow: a bill that turns up after the rest have
already been labelled, and a sticker torn off a carton in the lorry.

The rule these tests hold is that a reprint is IDENTICAL, not merely similar.
Two different stickers for the same carton is worse than a missing one — the
godown sorts by whichever it reads first, and nobody knows which that was.
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
    "freight_legs",
    "tracking_sessions",
)


@pytest.fixture()
def scene(client):
    """One loaded freight with a four-box bill on it, and one bill still
    sitting in the godown unassigned."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.consignment import Box, Consignment
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence
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
        lr_no="TE/0042",
    )
    db.add(freight)
    db.flush()

    # Two stops, so the colour and sequence on the reprint have to be the right
    # stop's rather than simply the first one's.
    bills = {}
    for seq, consignee, boxes in ((1, anand, 4), (2, beena, 2)):
        point = FreightPoint(
            freight_id=freight.id,
            sequence=seq,
            consignee_id=consignee.id,
            loaded_box_count=boxes,
            floor_number=2 if seq == 1 else 0,
        )
        db.add(point)
        db.flush()

        consignment = Consignment(
            vendor_division_id=division.id,
            warehouse_id=warehouse.id,
            consignee_id=consignee.id,
            freight_point_id=point.id,
            vendor_bill_no=f"BILL-{seq}",
            bill_date=date.today(),
            declared_box_count=boxes,
        )
        db.add(consignment)
        db.flush()
        bills[seq] = str(consignment.id)

        # Added out of order on purpose: the printed stack must come back
        # sorted, not in insertion order.
        for n in reversed(range(1, boxes + 1)):
            db.add(
                Box(
                    consignment_id=consignment.id,
                    item_no=n,
                    barcode=f"TE-STOP{seq}-{n:03d}",
                    item_name=f"Chair {n}",
                )
            )

    # The bill nobody has put on a freight yet.
    loose = Consignment(
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        consignee_id=beena.id,
        freight_point_id=None,
        vendor_bill_no="BILL-LOOSE",
        bill_date=date.today(),
        declared_box_count=2,
    )
    db.add(loose)
    db.flush()
    for n in (1, 2):
        db.add(
            Box(
                consignment_id=loose.id,
                item_no=n,
                barcode=f"TE-LOOSE-{n:03d}",
                item_name="Wardrobe panel",
            )
        )

    db.commit()
    data = {
        "freight": str(freight.id),
        "bill_1": bills[1],
        "bill_2": bills[2],
        "loose": str(loose.id),
    }
    db.close()
    return data


def _labels(client, headers, consignment_id: str):
    return client.get(f"/api/consignments/{consignment_id}/labels", headers=headers)


# ---------------------------------------------------------------------------
# What comes back
# ---------------------------------------------------------------------------


def test_one_sticker_per_box_on_the_bill(client, scene, auth):
    res = _labels(client, auth, scene["bill_1"])
    assert res.status_code == 200, res.text

    labels = res.json()
    assert len(labels) == 4, "four boxes on the bill, four stickers"
    assert {label["vendor_bill_no"] for label in labels} == {"BILL-1"}


def test_the_stack_comes_back_in_box_order(client, scene, auth):
    """The crew sorts them in the order they come off the printer."""
    labels = _labels(client, auth, scene["bill_1"]).json()
    assert [label["item_no"] for label in labels] == [1, 2, 3, 4]


def test_each_sticker_says_which_of_how_many(client, scene, auth):
    """"3 of 4" is how a short delivery is spotted at the door."""
    labels = _labels(client, auth, scene["bill_1"]).json()
    assert {label["of_total"] for label in labels} == {4}


def test_only_this_bills_boxes(client, scene, auth):
    """The other stop's cartons must not come out on this reprint."""
    labels = _labels(client, auth, scene["bill_1"]).json()
    assert all(label["barcode"].startswith("TE-STOP1-") for label in labels)


def test_the_sticker_carries_what_the_sorter_reads(client, scene, auth):
    labels = _labels(client, auth, scene["bill_2"]).json()
    first = labels[0]

    assert first["point_sequence"] == 2, "the second stop, not the first"
    assert first["point_colour"].startswith("#")
    assert first["consignee_name"] == "Beena Stores"
    assert first["city"] == "Kannur"
    assert first["trip_no"] == "Y26000001"
    assert first["lr_no"] == "TE/0042"


def test_the_floor_is_on_the_sticker(client, scene, auth):
    """The climb is what the unloading charge is argued over, so the crew needs
    it before they pick the carton up."""
    labels = _labels(client, auth, scene["bill_1"]).json()
    assert labels[0]["floor_number"] == 2


# ---------------------------------------------------------------------------
# The rule that matters: a reprint is identical
# ---------------------------------------------------------------------------


def test_a_reprint_matches_the_freight_print_exactly(client, scene, auth):
    """Field for field. Two different stickers for one carton is worse than
    none, because the godown sorts by whichever it reads first."""
    whole = {
        label["barcode"]: label
        for label in client.get(
            f"/api/freights/{scene['freight']}/labels", headers=auth
        ).json()
    }

    for bill in (scene["bill_1"], scene["bill_2"]):
        for label in _labels(client, auth, bill).json():
            assert label["barcode"] in whole, "a barcode the freight print lacks"
            assert label == whole[label["barcode"]], "the reprint differs"


def test_the_two_bills_together_are_the_whole_freight(client, scene, auth):
    """Nothing is dropped and nothing is invented."""
    whole = client.get(
        f"/api/freights/{scene['freight']}/labels", headers=auth
    ).json()
    one = _labels(client, auth, scene["bill_1"]).json()
    two = _labels(client, auth, scene["bill_2"]).json()

    assert len(one) + len(two) == len(whole)


# ---------------------------------------------------------------------------
# A bill not yet on a freight
# ---------------------------------------------------------------------------


def test_a_loose_bill_still_lists_its_boxes(client, scene, auth):
    """Worth having: this is the bill most likely to need labelling, because it
    missed the batch the rest of the freight went out in."""
    res = _labels(client, auth, scene["loose"])
    assert res.status_code == 200, res.text
    assert len(res.json()) == 2


def test_a_loose_bill_does_not_invent_a_point_or_a_trip(client, scene, auth):
    """A sticker that looks complete and sorts to nowhere is the worst outcome
    here, so the three things that do not exist yet come back blank.
    """
    label = _labels(client, auth, scene["loose"]).json()[0]

    assert label["point_sequence"] == 0, "there is no stop number yet"
    assert label["trip_no"] == "", "there is no trip yet"
    assert label["lr_no"] is None


def test_a_loose_bill_still_names_the_consignee(client, scene, auth):
    """Who it is for is known from the bill itself, long before the freight."""
    label = _labels(client, auth, scene["loose"]).json()[0]
    assert label["consignee_name"] == "Beena Stores"
    assert label["city"] == "Kannur"
    assert label["vendor_bill_no"] == "BILL-LOOSE"


# ---------------------------------------------------------------------------
# Slips
# ---------------------------------------------------------------------------


def test_an_unknown_bill_is_404(client, scene, auth):
    res = client.get(
        "/api/consignments/00000000-0000-0000-0000-000000000000/labels", headers=auth
    )
    assert res.status_code == 404


def test_the_reprint_needs_a_login(client, scene):
    assert _labels(client, {}, scene["bill_1"]).status_code == 401


# ---------------------------------------------------------------------------
# A stop with no bills on it
# ---------------------------------------------------------------------------


def test_a_point_reports_its_bills_and_boxes(client, scene, auth):
    """The freight screen warns about an empty stop using these two numbers, so
    they have to be the bills actually attached rather than the planned count
    somebody typed when the trip was built."""
    freight = client.get(f"/api/freights/{scene['freight']}", headers=auth).json()
    points = {p["sequence"]: p for p in freight["points"]}

    assert points[1]["bill_count"] == 1
    assert points[1]["box_count"] == 4
    assert points[2]["bill_count"] == 1
    assert points[2]["box_count"] == 2


def test_a_point_with_no_bills_reports_zero(client, scene, auth):
    """The case the warning exists for: a freight built before its bills were
    attached produces no boxes, so no labels, and the sorting sheet is a row of
    zeroes with nothing saying why."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, GeoConfidence
    from app.models.freight import FreightPoint

    db = SessionLocal()
    lonely = Consignee(
        name="Nobody Yet",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Aluva",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add(lonely)
    db.flush()
    db.add(FreightPoint(freight_id=scene["freight"], sequence=3, consignee_id=lonely.id))
    db.commit()
    db.close()

    freight = client.get(f"/api/freights/{scene['freight']}", headers=auth).json()
    empty = next(p for p in freight["points"] if p["sequence"] == 3)

    assert empty["bill_count"] == 0
    assert empty["box_count"] == 0

    # And the freight-wide label print produces nothing for that stop.
    labels = client.get(f"/api/freights/{scene['freight']}/labels", headers=auth).json()
    assert all(label["point_sequence"] != 3 for label in labels)
