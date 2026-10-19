"""A day sheet that produces a trip somebody can actually run.

The sheet built the bills, the boxes, the freight and the stops in one action,
and all of that worked. What came out the other end was still missing two
things, and both only showed up once somebody tried to use the trip.

WHERE IS IT GOING
    A customer typed in on the sheet arrived with a name and nothing else, and
    the stop was created with no address at all. So the trip header said
    "Godrej OCP · Godrej Warehouse, Ernakulam" and never said Kottayam, the
    driver's screen had nothing to navigate to, and the charge sheet printed a
    blank location. A dealer's name is not a place.

WHAT IS ON THE BILL
    Six boxes says nothing about whether they are chairs or wardrobes, and
    unloading is priced per article. A furniture run reached the point with no
    articles to tick, so nothing could be charged for carrying it in.

Both are caught here because both are invisible at the moment of entry and
expensive an hour later, on the lorry.
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
    "unloading_item_rates",
    "freights",
    "freight_points",
    "consignments",
    "boxes",
    "freight_legs",
)


@pytest.fixture()
def setup(client, auth):
    """A furniture division with two priced articles, and nothing else."""
    from app.db.session import SessionLocal
    from app.models.rating import UnloadingItemRate
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

    for code, name in (("CHAIR", "Chair"), ("WARDROBE", "Wardrobe")):
        db.add(
            UnloadingItemRate(
                vendor_division_id=division.id,
                item_code=code,
                item_name=name,
                base_rate=50,
                per_floor_rate=10,
                driver_base_rate=30,
                driver_per_floor_rate=6,
                effective_from=date.today(),
                is_active=True,
            )
        )

    db.commit()
    data = {"division": str(division.id), "warehouse": str(warehouse.id)}
    db.close()
    return data


def _commit(client, auth, setup, rows, **extra):
    return client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": rows,
            "trip_date": date.today().isoformat(),
            **extra,
        },
        headers=auth,
    )


def _freight(freight_id):
    from app.db.session import SessionLocal
    from app.models.freight import Freight

    db = SessionLocal()
    try:
        freight = db.get(Freight, freight_id)
        return {
            "destination_text": freight.destination_text,
            "points": [
                {
                    "address_snapshot": p.address_snapshot,
                    "loaded_box_count": p.loaded_box_count,
                }
                for p in freight.points
            ],
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Where it is going
# ---------------------------------------------------------------------------


def test_a_new_customers_address_reaches_the_stop(client, setup, auth):
    """Typed once on the sheet, and the driver has somewhere to drive to."""
    res = _commit(
        client,
        auth,
        setup,
        [
            {
                "vendor_bill_no": "GDJ/8870",
                "box_count": 6,
                "new_customer": {
                    "name": "Hafrin",
                    "city": "Kottayam",
                    "address": "Shop 4, MC Road, Kottayam",
                },
            }
        ],
    )
    assert res.status_code == 201, res.text

    out = _freight(res.json()["freight_id"])
    assert out["points"][0]["address_snapshot"] == "Shop 4, MC Road, Kottayam"


def test_the_trip_says_where_it_is_going_before_it_leaves(client, setup, auth):
    """The header read "Godrej OCP · Godrej Warehouse" and never said Kottayam.

    `destination_text` was rendered at dispatch, so a PLANNED trip — which is
    every trip somebody is looking at while deciding whether to send it —
    named only the vendor and the godown it was leaving.
    """
    res = _commit(
        client,
        auth,
        setup,
        [
            {
                "vendor_bill_no": "GDJ/8870",
                "box_count": 6,
                "new_customer": {"name": "Hafrin", "city": "Kottayam"},
            },
            {
                "vendor_bill_no": "GDJ/8871",
                "box_count": 2,
                "new_customer": {"name": "Shaji Furniture", "city": "Thrissur"},
            },
        ],
    )
    assert res.status_code == 201, res.text

    assert _freight(res.json()["freight_id"])["destination_text"] == "Kottayam, Thrissur"


def test_a_customer_with_no_city_falls_back_to_their_name(client, setup, auth):
    """Something on the header beats nothing, and a name is at least a clue."""
    res = _commit(
        client,
        auth,
        setup,
        [{"vendor_bill_no": "GDJ/8870", "box_count": 6, "new_customer": {"name": "Hafrin"}}],
    )
    assert _freight(res.json()["freight_id"])["destination_text"] == "Hafrin"


def test_a_place_is_not_repeated_when_two_dealers_share_it(client, setup, auth):
    """"Kottayam, Kottayam, Kottayam" is not a destination."""
    res = _commit(
        client,
        auth,
        setup,
        [
            {
                "vendor_bill_no": "GDJ/1",
                "box_count": 1,
                "new_customer": {"name": "One", "city": "Kottayam"},
            },
            {
                "vendor_bill_no": "GDJ/2",
                "box_count": 1,
                "new_customer": {"name": "Two", "city": "Kottayam"},
            },
        ],
    )
    assert _freight(res.json()["freight_id"])["destination_text"] == "Kottayam"


# ---------------------------------------------------------------------------
# What is on the bill
# ---------------------------------------------------------------------------


def _boxes(client, auth, consignment_bill):
    from app.db.session import SessionLocal
    from app.models.consignment import Box, Consignment

    db = SessionLocal()
    try:
        consignment = (
            db.execute(
                __import__("sqlalchemy")
                .select(Consignment)
                .where(Consignment.vendor_bill_no == consignment_bill)
            )
            .scalars()
            .first()
        )
        rows = (
            db.execute(
                __import__("sqlalchemy")
                .select(Box)
                .where(Box.consignment_id == consignment.id)
            )
            .scalars()
            .all()
        )
        return [(b.item_code, b.item_name) for b in rows]
    finally:
        db.close()


def test_articles_become_one_named_box_each(client, setup, auth):
    """A carton of furniture IS the article, and what it is decides its price."""
    res = _commit(
        client,
        auth,
        setup,
        [
            {
                "vendor_bill_no": "GDJ/8870",
                "articles": [
                    {"item_code": "CHAIR", "quantity": 4},
                    {"item_code": "WARDROBE", "quantity": 2},
                ],
                "new_customer": {"name": "Hafrin", "city": "Kottayam"},
            }
        ],
    )
    assert res.status_code == 201, res.text
    assert res.json()["box_count"] == 6

    boxes = _boxes(client, auth, "GDJ/8870")
    assert len(boxes) == 6
    assert boxes.count(("CHAIR", "Chair")) == 4
    assert boxes.count(("WARDROBE", "Wardrobe")) == 2


def test_the_articles_decide_the_box_count(client, setup, auth):
    """Two figures that can disagree is one too many."""
    res = _commit(
        client,
        auth,
        setup,
        [
            {
                "vendor_bill_no": "GDJ/8870",
                "articles": [{"item_code": "CHAIR", "quantity": 3}],
                "new_customer": {"name": "Hafrin", "city": "Kottayam"},
            }
        ],
    )
    assert res.json()["box_count"] == 3
    assert _freight(res.json()["freight_id"])["points"][0]["loaded_box_count"] == 3


def test_a_box_count_that_contradicts_the_articles_is_refused(client, setup, auth):
    """Guessing which is right gets either the labels or the charge wrong."""
    res = _commit(
        client,
        auth,
        setup,
        [
            {
                "vendor_bill_no": "GDJ/8870",
                "box_count": 10,
                "articles": [{"item_code": "CHAIR", "quantity": 3}],
                "new_customer": {"name": "Hafrin"},
            }
        ],
    )
    assert res.status_code == 422
    assert "add up to 3" in res.json()["detail"]


def test_a_row_with_neither_boxes_nor_articles_is_refused(client, setup, auth):
    res = _commit(
        client,
        auth,
        setup,
        [{"vendor_bill_no": "GDJ/8870", "new_customer": {"name": "Hafrin"}}],
    )
    assert res.status_code == 422
    assert "no boxes and no articles" in res.json()["detail"]


def test_a_plain_box_count_still_works(client, setup, auth):
    """Spare parts are counted in cartons and priced by nothing else."""
    res = _commit(
        client,
        auth,
        setup,
        [
            {
                "vendor_bill_no": "GDJ/8870",
                "box_count": 6,
                "new_customer": {"name": "Hafrin", "city": "Kottayam"},
            }
        ],
    )
    assert res.status_code == 201, res.text
    assert res.json()["box_count"] == 6
    assert len(_boxes(client, auth, "GDJ/8870")) == 6


def test_articles_priced_for_this_vendor_carry_their_proper_names(client, setup, auth):
    """The label on the carton reads "Wardrobe", not "WARDROBE"."""
    _commit(
        client,
        auth,
        setup,
        [
            {
                "vendor_bill_no": "GDJ/8870",
                "articles": [{"item_code": "WARDROBE", "quantity": 1}],
                "new_customer": {"name": "Hafrin"},
            }
        ],
    )
    assert _boxes(client, auth, "GDJ/8870") == [("WARDROBE", "Wardrobe")]
