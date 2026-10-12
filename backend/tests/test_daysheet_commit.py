"""A morning's bills entered in one action, over HTTP.

What this replaces is thirty trips through a dialog, then building the freight
separately, then attaching each bill to its stop separately again — the last
being the step that gets missed, and the one that leaves a sorting sheet full
of zeroes.

So the test that matters is not that rows appear. It is that what comes out is
ready to work with: the bills exist, the boxes exist, the freight exists, the
stops are in order, and every bill is ATTACHED to its stop. Anything less and
the person is back on the old path, hunting for what was left half done.

The second rule: all or nothing. Half a day sheet is worse than none, because
nobody can tell by looking which half went in, and the natural response is to
type it all again and end up with the good half twice.
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
    "vehicle_pings",
)


@pytest.fixture()
def setup(client, auth):
    """A division, a warehouse, and three customers already on file."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, GeoConfidence
    from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()
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
        is_active=True,
    )
    warehouse = VendorWarehouse(vendor_id=vendor.id, name="Kochi godown", code="KOCHI")
    db.add_all([division, warehouse])
    db.flush()

    ids = {}
    for name, city in (
        ("Kannur Distribution Centre", "Kannur"),
        ("Kozhikode Service Point", "Kozhikode"),
        ("Rinshad Km", "Aluva"),
    ):
        c = Consignee(
            name=name,
            type=ConsigneeType.RETAIL_CUSTOMER,
            city=city,
            geo_confidence=GeoConfidence.UNVERIFIED,
            is_active=True,
        )
        db.add(c)
        db.flush()
        ids[name] = str(c.id)

    db.commit()
    data = {
        "division": str(division.id),
        "warehouse": str(warehouse.id),
        "customers": ids,
    }
    db.close()
    return data


SHEET = """GDJ/8870 Rinshad Km 6
GDJ/8871 Kannur DC 4 chairs
gdj 8872 kozikode srvce 2
GDJ/8873 Kannur DC 3"""


def _parse(client, auth, setup, text=SHEET):
    return client.post(
        "/api/daysheet/parse",
        json={"text": text, "vendor_division_id": setup["division"]},
        headers=auth,
    )


def _rows_from(parsed):
    return [
        {
            "vendor_bill_no": line["vendor_bill_no"],
            "box_count": line["box_count"],
            "item_name": line["item_name"],
            "consignee_id": line["match"]["consignee_id"],
        }
        for line in parsed["lines"]
    ]


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def test_the_sheet_is_read_against_the_real_customer_list(client, setup, auth):
    res = _parse(client, auth, setup)
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["bill_count"] == 4
    assert body["box_count"] == 15
    assert body["stop_count"] == 3, "two bills for Kannur are one stop"
    assert body["needs_attention"] == 0


def test_a_bill_already_entered_is_caught_before_typing_more(client, setup, auth):
    """Finding this out after forty lines is the worst possible moment."""
    first = _parse(client, auth, setup).json()
    client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": _rows_from(first),
        },
        headers=auth,
    )

    again = _parse(client, auth, setup).json()
    assert again["needs_attention"] == 4
    assert "already entered" in again["lines"][0]["problems"][0]


def test_parsing_creates_nothing(client, setup, auth):
    _parse(client, auth, setup)
    assert client.get("/api/consignments", headers=auth).json() == []


# ---------------------------------------------------------------------------
# What one action produces
# ---------------------------------------------------------------------------


@pytest.fixture()
def committed(client, setup, auth):
    parsed = _parse(client, auth, setup).json()
    res = client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "trip_date": date.today().isoformat(),
            "rows": _rows_from(parsed),
            "create_freight": True,
            "stop_order": [
                setup["customers"]["Kozhikode Service Point"],
                setup["customers"]["Kannur Distribution Centre"],
                setup["customers"]["Rinshad Km"],
            ],
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_the_bills_are_created(client, setup, auth, committed):
    assert committed["consignment_count"] == 4
    assert len(client.get("/api/consignments", headers=auth).json()) == 4


def test_the_boxes_are_created(client, setup, auth, committed):
    assert committed["box_count"] == 15


def test_the_freight_is_created_with_one_stop_per_customer(client, setup, auth, committed):
    """Not one per bill. The vendor is charged per point, so splitting a
    customer's two bills into two stops would overcharge them."""
    assert committed["trip_no"]
    assert committed["stop_count"] == 3


def test_every_bill_is_attached_to_its_stop(client, setup, auth, committed):
    """The step that gets missed, and the whole reason this screen exists."""
    bills = client.get("/api/consignments", headers=auth).json()
    assert all(b["freight_point_id"] for b in bills), "a bill was left unattached"


def test_the_freight_is_ready_to_label(client, setup, auth, committed):
    """End to end: the thing the old path could not reach without three more
    screens."""
    labels = client.get(
        f"/api/freights/{committed['freight_id']}/labels", headers=auth
    ).json()
    assert len(labels) == 15, "15 boxes should produce 15 stickers"
    assert all(label["point_sequence"] >= 1 for label in labels)
    assert len({label["barcode"] for label in labels}) == 15


def test_the_stops_are_in_the_order_asked_for(client, setup, auth, committed):
    freight = client.get(
        f"/api/freights/{committed['freight_id']}", headers=auth
    ).json()
    names = [p["consignee_name"] for p in sorted(freight["points"], key=lambda p: p["sequence"])]
    assert names == [
        "Kozhikode Service Point",
        "Kannur Distribution Centre",
        "Rinshad Km",
    ]


def test_the_stop_carries_both_of_that_customers_bills(client, setup, auth, committed):
    freight = client.get(
        f"/api/freights/{committed['freight_id']}", headers=auth
    ).json()
    kannur = next(p for p in freight["points"] if p["consignee_name"].startswith("Kannur"))
    assert kannur["bill_count"] == 2
    assert kannur["box_count"] == 7


# ---------------------------------------------------------------------------
# A customer nobody has entered yet
# ---------------------------------------------------------------------------


def test_a_new_customer_is_created_with_the_bill(client, setup, auth):
    res = client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": [
                {
                    "vendor_bill_no": "GDJ/8880",
                    "box_count": 3,
                    "new_customer": {"name": "Vadakara Furniture House", "city": "Vadakara"},
                }
            ],
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text
    assert res.json()["customers_created"] == 1

    names = [c["name"] for c in client.get("/api/consignees", headers=auth).json()]
    assert "Vadakara Furniture House" in names


def test_a_customer_entered_this_way_is_marked_unverified(client, setup, auth):
    """Typed off a bill with nobody looking at a map. It should show up to be
    pinned rather than be trusted as a delivery location."""
    client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": [
                {
                    "vendor_bill_no": "GDJ/8881",
                    "box_count": 1,
                    "new_customer": {"name": "Vadakara Furniture House"},
                }
            ],
        },
        headers=auth,
    )
    created = next(
        c
        for c in client.get("/api/consignees", headers=auth).json()
        if c["name"] == "Vadakara Furniture House"
    )
    assert created["geo_confidence"] == "UNVERIFIED"


# ---------------------------------------------------------------------------
# All or nothing
# ---------------------------------------------------------------------------


def test_a_duplicate_within_the_sheet_is_refused(client, setup, auth):
    res = client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": [
                {"vendor_bill_no": "GDJ/9001", "box_count": 2,
                 "consignee_id": setup["customers"]["Rinshad Km"]},
                {"vendor_bill_no": "GDJ/9001", "box_count": 3,
                 "consignee_id": setup["customers"]["Rinshad Km"]},
            ],
        },
        headers=auth,
    )
    assert res.status_code == 409
    assert "twice" in res.json()["detail"]


def test_a_refused_sheet_creates_nothing_at_all(client, setup, auth):
    """The rule. Half a sheet is worse than none: nobody can tell which half
    went in, so it gets typed again and the good half lands twice."""
    client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": [
                {"vendor_bill_no": "GDJ/9002", "box_count": 2,
                 "consignee_id": setup["customers"]["Rinshad Km"]},
                {"vendor_bill_no": "GDJ/9002", "box_count": 3,
                 "consignee_id": setup["customers"]["Rinshad Km"]},
            ],
        },
        headers=auth,
    )
    assert client.get("/api/consignments", headers=auth).json() == []
    assert client.get("/api/freights", headers=auth).json() == []


def test_a_bill_with_no_customer_is_refused(client, setup, auth):
    res = client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": [{"vendor_bill_no": "GDJ/9003", "box_count": 2}],
        },
        headers=auth,
    )
    assert res.status_code == 422


def test_bills_can_be_entered_without_a_freight(client, setup, auth):
    """When the lorry is not decided yet. The bills wait, as they did before."""
    res = client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "create_freight": False,
            "rows": [
                {"vendor_bill_no": "GDJ/9004", "box_count": 2,
                 "consignee_id": setup["customers"]["Rinshad Km"]}
            ],
        },
        headers=auth,
    )
    assert res.status_code == 201
    assert res.json()["freight_id"] is None
    assert client.get("/api/consignments", headers=auth).json()[0]["freight_point_id"] is None


def test_the_day_sheet_needs_a_login(client, setup):
    assert client.post("/api/daysheet/parse", json={"text": "x"}).status_code == 401
    assert (
        client.post(
            "/api/daysheet/commit",
            json={"vendor_division_id": "x", "warehouse_id": "y", "rows": []},
        ).status_code
        in (401, 422)
    )


# ---------------------------------------------------------------------------
# A customer nobody has entered yet, end to end
# ---------------------------------------------------------------------------


NEW_CUSTOMER_SHEET = """GDJ/8880 Rinshad Km 2
GDJ/8881 Vadakara Furniture House 5"""


def test_an_unknown_name_is_not_forced_onto_the_nearest_match(client, setup, auth):
    """The failure that matters. A new dealer whose name is vaguely like an
    existing one must not quietly inherit that customer's address — the cartons
    would go to the wrong town."""
    parsed = _parse(client, auth, setup, NEW_CUSTOMER_SHEET).json()
    new_line = next(l for l in parsed["lines"] if l["vendor_bill_no"] == "GDJ/8881")

    assert new_line["match"]["consignee_id"] is None
    assert new_line["customer_text"] == "Vadakara Furniture House"


def test_the_sheet_commits_with_a_mix_of_known_and_new(client, setup, auth):
    """One known customer and one new one, in the same action."""
    parsed = _parse(client, auth, setup, NEW_CUSTOMER_SHEET).json()

    rows = []
    for line in parsed["lines"]:
        match = line["match"]
        known = match and match["consignee_id"]
        rows.append(
            {
                "vendor_bill_no": line["vendor_bill_no"],
                "box_count": line["box_count"],
                "consignee_id": match["consignee_id"] if known else None,
                "new_customer": None if known else {"name": line["customer_text"]},
            }
        )

    res = client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": rows,
            "create_freight": True,
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text

    body = res.json()
    assert body["consignment_count"] == 2
    assert body["customers_created"] == 1, "only the unknown one is created"
    assert body["stop_count"] == 2


def test_the_new_customer_gets_a_stop_on_the_freight(client, setup, auth):
    """Not dropped from the route for lacking an id when the sheet was typed."""
    parsed = _parse(client, auth, setup, NEW_CUSTOMER_SHEET).json()
    rows = [
        {
            "vendor_bill_no": l["vendor_bill_no"],
            "box_count": l["box_count"],
            "consignee_id": (l["match"]["consignee_id"] if l["match"] else None),
            "new_customer": (
                None
                if (l["match"] and l["match"]["consignee_id"])
                else {"name": l["customer_text"], "city": "Vadakara"}
            ),
        }
        for l in parsed["lines"]
    ]
    out = client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": rows,
            "create_freight": True,
        },
        headers=auth,
    ).json()

    freight = client.get(f"/api/freights/{out['freight_id']}", headers=auth).json()
    names = {p["consignee_name"] for p in freight["points"]}
    assert "Vadakara Furniture House" in names

    stop = next(p for p in freight["points"] if p["consignee_name"] == "Vadakara Furniture House")
    assert stop["bill_count"] == 1
    assert stop["box_count"] == 5


def test_the_new_customers_boxes_get_stickers(client, setup, auth):
    """End to end: a dealer who did not exist when the sheet was typed has
    printable labels by the time it is committed."""
    parsed = _parse(client, auth, setup, NEW_CUSTOMER_SHEET).json()
    rows = [
        {
            "vendor_bill_no": l["vendor_bill_no"],
            "box_count": l["box_count"],
            "consignee_id": (l["match"]["consignee_id"] if l["match"] else None),
            "new_customer": (
                None
                if (l["match"] and l["match"]["consignee_id"])
                else {"name": l["customer_text"]}
            ),
        }
        for l in parsed["lines"]
    ]
    out = client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": rows,
            "create_freight": True,
        },
        headers=auth,
    ).json()

    labels = client.get(f"/api/freights/{out['freight_id']}/labels", headers=auth).json()
    theirs = [l for l in labels if l["consignee_name"] == "Vadakara Furniture House"]
    assert len(theirs) == 5
    assert all(l["point_sequence"] >= 1 for l in theirs), "a sticker that sorts nowhere"


def test_a_corrected_name_is_what_gets_created(client, setup, auth):
    """The parser's guess at a name it has never seen is where it is least
    reliable, so the screen lets it be corrected first."""
    res = client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": [
                {
                    "vendor_bill_no": "GDJ/8882",
                    "box_count": 1,
                    "new_customer": {"name": "Vadakara Furniture House"},
                }
            ],
        },
        headers=auth,
    )
    assert res.status_code == 201

    names = [c["name"] for c in client.get("/api/consignees", headers=auth).json()]
    assert "Vadakara Furniture House" in names


def test_two_bills_for_the_same_new_customer_make_one_customer(client, setup, auth):
    """Typing the name twice must not create the dealer twice — the second bill
    would then be a separate stop and the vendor charged for two."""
    res = client.post(
        "/api/daysheet/commit",
        json={
            "vendor_division_id": setup["division"],
            "warehouse_id": setup["warehouse"],
            "rows": [
                {
                    "vendor_bill_no": "GDJ/8883",
                    "box_count": 2,
                    "new_customer": {"name": "Vadakara Furniture House"},
                },
                {
                    "vendor_bill_no": "GDJ/8884",
                    "box_count": 3,
                    "new_customer": {"name": "Vadakara Furniture House"},
                },
            ],
            "create_freight": True,
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text

    body = res.json()
    assert body["customers_created"] == 1, "created the same dealer twice"
    assert body["stop_count"] == 1, "one customer is one stop, however many bills"
