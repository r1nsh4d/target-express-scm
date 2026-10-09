"""Billing some of the work and not the rest, and recording what came back.

The period sweep is the right default and the wrong thing when one freight is
disputed, waiting on a toll receipt, or simply belongs on next month's bill.

Three rules these tests hold:

  * A freight that was NOT selected stays COMPLETED and turns up on the next
    run. Silently billing it, or silently losing it, are both worse than
    refusing.
  * Dropping a line re-adds the totals. A document whose lines do not sum to
    its total is the one thing a vendor's accounts team is certain to notice.
  * What is received is not what was invoiced. Transport vendors deduct TDS at
    source, so the receipt is smaller than the bill and the gap has to be
    visible rather than inferred.
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
def scene(client, auth):
    """Three completed freights for one division, all billable."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence
    from app.models.fleet import Driver, Vehicle, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.rating import RateCard
    from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()
    first = date.today() - timedelta(days=10)

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

    db.add(
        RateCard(
            vendor_division_id=division.id,
            base_trip_amount=Decimal("1867"),
            included_km=60,
            included_points=3,
            extra_km_rate=Decimal("17"),
            extra_point_rate=Decimal("175"),
            effective_from=first - timedelta(days=30),
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
    consignee = Consignee(
        name="Kannur Distribution Centre",
        type=ConsigneeType.DISTRIBUTION_CENTER,
        city="Kannur",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([vehicle, driver, consignee])
    db.flush()

    ids = []
    for n in range(3):
        trip_day = first + timedelta(days=n)
        freight = Freight(
            trip_no=f"Y2600800{n + 1}",
            trip_date=trip_day,
            vendor_division_id=division.id,
            warehouse_id=warehouse.id,
            status=FreightStatus.COMPLETED,
            point_count=1,
            total_km=100 + n * 10,
            lr_no=str(800 + n),
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
                start_odometer=1000 * (n + 1),
                end_odometer=1000 * (n + 1) + freight.total_km,
                leg_distance_km=freight.total_km,
            )
        )
        ids.append(str(freight.id))

    db.commit()
    data = {
        "division": str(division.id),
        "freights": ids,
        "period_from": (first - timedelta(days=1)).isoformat(),
        "period_to": date.today().isoformat(),
    }
    db.close()
    return data


def _status(freight_id: str) -> str:
    from app.db.session import SessionLocal
    from app.models.freight import Freight

    db = SessionLocal()
    try:
        return db.get(Freight, freight_id).status
    finally:
        db.close()


def _generate(client, auth, scene, freight_ids=None):
    body = {
        "vendor_division_id": scene["division"],
        "period_from": scene["period_from"],
        "period_to": scene["period_to"],
    }
    if freight_ids is not None:
        body["freight_ids"] = freight_ids
    return client.post("/api/invoices", json=body, headers=auth)


# ---------------------------------------------------------------------------
# The preview is what the ticking is done on
# ---------------------------------------------------------------------------


def test_the_preview_names_each_freight(client, scene, auth):
    """Without an id per line the screen cannot tick one."""
    res = client.post(
        "/api/invoices/preview",
        json={
            "vendor_division_id": scene["division"],
            "period_from": scene["period_from"],
            "period_to": scene["period_to"],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    lines = res.json()["lines"]
    assert len(lines) == 3
    assert {line["freight_id"] for line in lines} == set(scene["freights"])


# ---------------------------------------------------------------------------
# Billing only what was selected
# ---------------------------------------------------------------------------


def test_only_the_selected_freights_are_billed(client, scene, auth):
    res = _generate(client, auth, scene, [scene["freights"][0], scene["freights"][2]])
    assert res.status_code == 201, res.text
    assert res.json()["line_count"] == 2


def test_the_unselected_freight_stays_unbilled(client, scene, auth):
    """The rule the whole feature exists for."""
    _generate(client, auth, scene, [scene["freights"][0], scene["freights"][2]])

    assert _status(scene["freights"][0]) == "BILLED"
    assert _status(scene["freights"][1]) == "COMPLETED"
    assert _status(scene["freights"][2]) == "BILLED"


def test_the_one_left_out_can_be_billed_afterwards(client, scene, auth):
    """Left out, not lost."""
    _generate(client, auth, scene, [scene["freights"][0], scene["freights"][2]])

    res = _generate(client, auth, scene, [scene["freights"][1]])
    assert res.status_code == 201, res.text
    assert res.json()["line_count"] == 1


def test_the_period_follows_the_freights_on_the_invoice(client, scene, auth):
    """An invoice that says 01 Aug to 07 Oct but carries one September trip
    invites the question of where the rest went."""
    chosen = scene["freights"][1]
    body = _generate(client, auth, scene, [chosen]).json()
    assert body["period_from"] == body["period_to"], "one trip, one day"


def test_a_freight_already_billed_is_refused_not_duplicated(client, scene, auth):
    _generate(client, auth, scene, [scene["freights"][0]])

    res = _generate(client, auth, scene, [scene["freights"][0]])
    assert res.status_code == 409
    assert "already on an invoice" in res.json()["detail"]


def test_selecting_nothing_is_refused(client, scene, auth):
    res = _generate(client, auth, scene, [])
    assert res.status_code == 409


def test_the_period_sweep_still_works(client, scene, auth):
    """Leaving freight_ids out keeps the old behaviour."""
    res = _generate(client, auth, scene)
    assert res.status_code == 201, res.text
    assert res.json()["line_count"] == 3


# ---------------------------------------------------------------------------
# Billing one freight from the freight itself
# ---------------------------------------------------------------------------


def test_a_single_freight_can_be_billed_directly(client, scene, auth):
    res = client.post(
        f"/api/freights/{scene['freights'][1]}/bill", json={}, headers=auth
    )
    assert res.status_code == 201, res.text
    assert res.json()["line_count"] == 1
    assert _status(scene["freights"][1]) == "BILLED"


def test_billing_one_freight_leaves_the_others_alone(client, scene, auth):
    client.post(f"/api/freights/{scene['freights'][1]}/bill", json={}, headers=auth)
    assert _status(scene["freights"][0]) == "COMPLETED"
    assert _status(scene["freights"][2]) == "COMPLETED"


def test_a_freight_that_is_not_complete_cannot_be_billed(client, scene, auth):
    """BILLED must always have a finished trip behind it."""
    from app.db.session import SessionLocal
    from app.models.enums import FreightStatus
    from app.models.freight import Freight

    db = SessionLocal()
    f = db.get(Freight, scene["freights"][0])
    f.status = FreightStatus.IN_TRANSIT
    db.commit()
    db.close()

    res = client.post(f"/api/freights/{scene['freights'][0]}/bill", json={}, headers=auth)
    assert res.status_code == 409
    assert "completed" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Editing a draft
# ---------------------------------------------------------------------------


def test_a_line_can_be_taken_off_a_draft(client, scene, auth):
    inv = _generate(client, auth, scene).json()
    line = inv["lines"][0]

    res = client.delete(
        f"/api/invoices/{inv['id']}/lines/{line['id']}", headers=auth
    )
    assert res.status_code == 200, res.text
    assert res.json()["line_count"] == 2


def test_removing_a_line_gives_that_freight_back(client, scene, auth):
    inv = _generate(client, auth, scene).json()
    line = next(ln for ln in inv["lines"] if ln["trip_no"] == "Y26008002")

    client.delete(f"/api/invoices/{inv['id']}/lines/{line['id']}", headers=auth)
    assert _status(scene["freights"][1]) == "COMPLETED"


def test_removing_a_line_re_adds_the_totals(client, scene, auth):
    """A document whose lines do not sum to its total is the one thing the
    vendor's accounts team is certain to query."""
    inv = _generate(client, auth, scene).json()
    line = inv["lines"][0]

    after = client.delete(
        f"/api/invoices/{inv['id']}/lines/{line['id']}", headers=auth
    ).json()

    lines_sum = sum(Decimal(ln["line_total"]) for ln in after["lines"])
    assert Decimal(after["taxable_value"]) == lines_sum
    expected = (
        Decimal(after["taxable_value"])
        + Decimal(after["cgst"])
        + Decimal(after["sgst"])
        + Decimal(after["igst"])
    )
    assert Decimal(after["total"]) == expected


def test_removing_a_line_renumbers_the_rest(client, scene, auth):
    """Serial numbers on a tax invoice run 1..n with no gaps."""
    inv = _generate(client, auth, scene).json()
    after = client.delete(
        f"/api/invoices/{inv['id']}/lines/{inv['lines'][0]['id']}", headers=auth
    ).json()
    assert [ln["sl_no"] for ln in after["lines"]] == [1, 2]


def test_the_last_line_cannot_be_removed(client, scene, auth):
    """An invoice with no lines is a number with a total of zero. Discard it."""
    inv = _generate(client, auth, scene, [scene["freights"][0]]).json()
    res = client.delete(
        f"/api/invoices/{inv['id']}/lines/{inv['lines'][0]['id']}", headers=auth
    )
    assert res.status_code == 409
    assert "Discard" in res.json()["detail"]


def test_an_issued_invoice_cannot_be_edited(client, scene, auth):
    inv = _generate(client, auth, scene).json()
    client.patch(f"/api/invoices/{inv['id']}", json={"status": "ISSUED"}, headers=auth)

    res = client.delete(
        f"/api/invoices/{inv['id']}/lines/{inv['lines'][0]['id']}", headers=auth
    )
    assert res.status_code == 409
    assert "Only a draft" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Money in
# ---------------------------------------------------------------------------


def _issue(client, auth, scene):
    inv = _generate(client, auth, scene).json()
    client.patch(f"/api/invoices/{inv['id']}", json={"status": "ISSUED"}, headers=auth)
    return inv


def test_recording_a_payment_marks_it_paid(client, scene, auth):
    inv = _issue(client, auth, scene)
    res = client.post(
        f"/api/invoices/{inv['id']}/payment",
        json={"paid_on": date.today().isoformat(), "payment_mode": "NEFT"},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "PAID"


def test_a_payment_shows_up_under_money_in(client, scene, auth):
    inv = _issue(client, auth, scene)
    client.post(
        f"/api/invoices/{inv['id']}/payment",
        json={"payment_mode": "NEFT", "payment_reference": "HDFC0099123"},
        headers=auth,
    )

    rows = client.get("/api/money-in", headers=auth).json()
    assert len(rows) == 1
    assert rows[0]["invoice_no"] == inv["invoice_no"]
    assert rows[0]["payment_reference"] == "HDFC0099123"


def test_a_tds_deduction_is_recorded_as_a_shortfall(client, scene, auth):
    """The case this exists for. A 1% TDS deduction means the bank credits less
    than the invoice, and the gap has to be visible rather than inferred."""
    inv = _issue(client, auth, scene)
    total = Decimal(inv["total"])
    received = (total - (total / 100)).quantize(Decimal("0.01"))

    client.post(
        f"/api/invoices/{inv['id']}/payment",
        json={"amount_received": str(received), "payment_mode": "NEFT"},
        headers=auth,
    )

    row = client.get("/api/money-in", headers=auth).json()[0]
    assert Decimal(row["invoiced"]) == total
    assert Decimal(row["received"]) == received
    assert Decimal(row["shortfall"]) == (total - received).quantize(Decimal("0.01"))


def test_paying_without_an_amount_assumes_the_whole_invoice(client, scene, auth):
    inv = _issue(client, auth, scene)
    client.post(f"/api/invoices/{inv['id']}/payment", json={}, headers=auth)

    row = client.get("/api/money-in", headers=auth).json()[0]
    assert Decimal(row["received"]) == Decimal(inv["total"])
    assert Decimal(row["shortfall"]) == 0


def test_more_than_the_invoice_is_refused(client, scene, auth):
    inv = _issue(client, auth, scene)
    res = client.post(
        f"/api/invoices/{inv['id']}/payment",
        json={"amount_received": str(Decimal(inv["total"]) + 1)},
        headers=auth,
    )
    assert res.status_code == 422


def test_a_draft_cannot_be_paid(client, scene, auth):
    """Money against a document nobody was given is the wrong invoice."""
    inv = _generate(client, auth, scene).json()
    res = client.post(f"/api/invoices/{inv['id']}/payment", json={}, headers=auth)
    assert res.status_code == 409
    assert "draft" in res.json()["detail"]


def test_unpaying_removes_it_from_money_in(client, scene, auth):
    """An invoice that is no longer paid but still carries a payment date would
    keep showing under money in and the reconciliation would never balance."""
    inv = _issue(client, auth, scene)
    client.post(f"/api/invoices/{inv['id']}/payment", json={}, headers=auth)
    assert len(client.get("/api/money-in", headers=auth).json()) == 1

    client.patch(f"/api/invoices/{inv['id']}", json={"status": "SENT"}, headers=auth)
    assert client.get("/api/money-in", headers=auth).json() == []


def test_marking_paid_by_status_still_records_a_receipt(client, scene, auth):
    """The one-button path must not leave a paid invoice off money in."""
    inv = _issue(client, auth, scene)
    client.patch(f"/api/invoices/{inv['id']}", json={"status": "PAID"}, headers=auth)

    rows = client.get("/api/money-in", headers=auth).json()
    assert len(rows) == 1
    assert Decimal(rows[0]["received"]) == Decimal(inv["total"])


def test_money_in_needs_a_login(client, scene):
    assert client.get("/api/money-in").status_code == 401
