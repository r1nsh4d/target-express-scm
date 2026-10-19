"""What one freight earned, what it cost, and what is left.

Three people ask about the same trip. The driver wants his rate, his
kilometres and his unloading, in that order, because that is the order he can
check them in. The office wants both sides and the gap between them.

The failure these guard against is the one where two screens each compute
their own version and quietly disagree, so:

  * THE DRIVER'S TOTAL AND THE OFFICE'S COST LINE ARE ONE NUMBER. Both come
    off `services.economics`.
  * EVERY LINE CARRIES ITS WORKING. `140 = 2 × 70` is checkable. `140` is
    something you either believe or ring somebody about.
  * THE VENDOR'S CHARGE AND THE DRIVER'S PAY COME OFF ONE COUNT. What he
    counted through the door, not what the bill said was sent — otherwise the
    margin on a point inverts the moment one carton is refused.
  * UNLOADING IS NOT COUNTED TWICE. The delivery form writes an expense row
    for the cash handed over and the payout carries the same money under
    LOADING_UNLOADING; adding both makes the best trips look like the worst.
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
TRIP_DAY = TODAY - timedelta(days=3)


@pytest.fixture()
def scene(client, auth):
    """A 100 km furniture run to one stop on the second floor, two chairs in.

    Chair: the vendor pays 50 on the ground plus 10 a floor, the driver is
    paid 30 plus 6. On the second floor that is 70 each against 42 each, so
    two chairs bill 140 and pay 84.

    Card: 1,867 covering 60 km and 3 points, 17 a km beyond, 175 a point.
    100 km is 40 over, so 680 of extra distance. One stop is inside the three.
    Driver: 2.50 a km, so 250 for driving.
    """
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import ConsigneeType, FreightStatus, GeoConfidence
    from app.models.fleet import Driver, DriverPayTerms, Vehicle, VehicleOwner, VehicleType
    from app.models.freight import Freight, FreightLeg, FreightPoint, PointUnloadingItem
    from app.models.rating import RateCard, UnloadingItemRate
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
        gst_rate_percent=Decimal("12"),
        is_active=True,
    )
    warehouse = VendorWarehouse(vendor_id=vendor.id, name="Kochi godown", code="KOCHI")
    dost = VehicleType(name="DOST", capacity_kg=1250)
    db.add_all([division, warehouse, dost])
    db.flush()

    db.add(
        RateCard(
            vendor_division_id=division.id,
            base_trip_amount=Decimal("1867"),
            included_km=60,
            included_points=3,
            extra_km_rate=Decimal("17"),
            extra_point_rate=Decimal("175"),
            unloading_basis="PER_ITEM_FLOOR",
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

    owner = VehicleOwner(name="Target Express", phone="9000000041", is_active=True)
    db.add(owner)
    db.flush()
    lorry = Vehicle(
        owner_id=owner.id,
        vehicle_type_id=dost.id,
        registration_no="KL07CW3317",
        lr_next_number=1,
        is_active=True,
    )
    driver = Driver(name="Suresh", phone="9000000032", is_active=True)
    consignee = Consignee(
        name="Kottayam Furniture Mart",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Kottayam",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([lorry, driver, consignee])
    db.flush()

    db.add(
        DriverPayTerms(
            driver_id=driver.id,
            per_km_amount=Decimal("2.50"),
            effective_from=TRIP_DAY - timedelta(days=30),
        )
    )

    freight = Freight(
        trip_no="Y26009001",
        trip_date=TRIP_DAY,
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.COMPLETED,
        point_count=1,
        total_km=100,
        destination_text="Kottayam",
    )
    db.add(freight)
    db.flush()

    point = FreightPoint(
        freight_id=freight.id,
        sequence=1,
        consignee_id=consignee.id,
        floor_number=2,
        has_lift=False,
        unloading_billed=Decimal("140.00"),
        unloading_paid=Decimal("84.00"),
    )
    db.add(point)
    db.flush()
    db.add(
        PointUnloadingItem(
            freight_point_id=point.id, item_code="CHAIR", item_name="Chair", quantity=2
        )
    )
    db.add(
        FreightLeg(
            freight_id=freight.id,
            sequence=1,
            vehicle_id=lorry.id,
            driver_id=driver.id,
            start_odometer=1000,
            end_odometer=1100,
            leg_distance_km=100,
        )
    )
    db.commit()

    data = {"freight": str(freight.id), "point": str(point.id), "driver": str(driver.id)}
    db.close()
    return data


def _economics(client, auth, scene):
    res = client.get(f"/api/freights/{scene['freight']}/economics", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# What the vendor pays, with the card's own figures named
# ---------------------------------------------------------------------------


def test_the_base_charge_says_what_it_covers(client, scene, auth):
    """"1,867" alone does not explain why a 40 km run bills the same as a 58."""
    revenue = _economics(client, auth, scene)["revenue"]
    base = revenue[0]

    assert Decimal(base["amount"]) == Decimal("1867.00")
    assert "60 km" in base["working"]
    assert "3 points" in base["working"]


def test_extra_distance_shows_the_multiplication(client, scene, auth):
    """40 km over 60, at 17 a km."""
    revenue = _economics(client, auth, scene)["revenue"]
    extra = next(line for line in revenue if line["label"] == "Extra distance")

    assert Decimal(extra["amount"]) == Decimal("680.00")
    assert "40 km" in extra["working"]
    assert "17.00" in extra["working"]


def test_a_charge_of_zero_still_explains_itself(client, scene, auth):
    """One stop against three included. The line stays, saying why it is nil."""
    revenue = _economics(client, auth, scene)["revenue"]
    points = next(line for line in revenue if line["label"] == "Extra points")

    assert Decimal(points["amount"]) == Decimal("0.00")
    assert "within the 3 included" in points["working"]


def test_unloading_is_billed_per_article_and_floor(client, scene, auth):
    e = _economics(client, auth, scene)
    unloading = next(line for line in e["revenue"] if line["label"] == "Unloading")

    assert Decimal(unloading["amount"]) == Decimal("140.00")
    assert "2 articles" in unloading["working"]
    assert Decimal(e["revenue_total"]) == Decimal("2687.00")


def test_a_trip_with_no_rate_card_says_so_instead_of_billing_nothing(client, scene, auth):
    from app.db.session import SessionLocal
    from app.models.rating import RateCard

    db = SessionLocal()
    try:
        for card in db.execute(__import__("sqlalchemy").select(RateCard)).scalars().all():
            card.is_active = False
        db.commit()
    finally:
        db.close()

    e = _economics(client, auth, scene)
    assert e["revenue"] == []
    assert Decimal(e["revenue_total"]) == Decimal("0.00")
    assert e["revenue_problem"] is not None
    assert "rate card" in e["revenue_problem"].lower()


# ---------------------------------------------------------------------------
# The unloading, both sides, off one count
# ---------------------------------------------------------------------------


def test_each_stop_shows_the_charge_the_pay_and_the_gap(client, scene, auth):
    """50+2×10 charged against 30+2×6 paid, twice over."""
    stop = _economics(client, auth, scene)["unloading_points"][0]

    assert stop["customer_name"] == "Kottayam Furniture Mart"
    assert stop["floor_number"] == 2
    assert Decimal(stop["charged"]) == Decimal("140.00")
    assert Decimal(stop["driver_pay"]) == Decimal("84.00")
    assert Decimal(stop["margin"]) == Decimal("56.00")

    article = stop["articles"][0]
    assert article["item_name"] == "Chair"
    assert article["quantity"] == 2
    assert Decimal(article["charged_each"]) == Decimal("70.00")
    assert Decimal(article["driver_each"]) == Decimal("42.00")
    assert article["floors_charged"] == 2


def test_the_drivers_count_beats_the_bill(client, scene, auth):
    """He counted two in. The bill saying five does not pay him for five."""
    from app.db.session import SessionLocal
    from app.models.consignment import Box, Consignment
    from app.models.freight import FreightPoint

    db = SessionLocal()
    try:
        point = db.get(FreightPoint, scene["point"])
        freight = point.freight
        consignment = Consignment(
            vendor_division_id=freight.vendor_division_id,
            warehouse_id=freight.warehouse_id,
            consignee_id=point.consignee_id,
            freight_point_id=point.id,
            vendor_bill_no="GJ/1001",
            bill_date=TRIP_DAY,
            declared_box_count=5,
        )
        db.add(consignment)
        db.flush()
        for n in range(5):
            db.add(
                Box(
                    consignment_id=consignment.id,
                    item_no=n + 1,
                    barcode=f"TX-CHAIR-{n + 1}",
                    item_code="CHAIR",
                )
            )
        db.commit()
    finally:
        db.close()

    stop = _economics(client, auth, scene)["unloading_points"][0]
    assert stop["articles"][0]["quantity"] == 2
    assert Decimal(stop["charged"]) == Decimal("140.00")


# ---------------------------------------------------------------------------
# What it costs, and what is left
# ---------------------------------------------------------------------------


def test_the_driving_cost_shows_his_rate_and_his_distance(client, scene, auth):
    """100 km at 2.50. Not a number he has to take on trust."""
    cost = _economics(client, auth, scene)["cost"]
    driving = next(line for line in cost if line["label"] == "Driving")

    assert Decimal(driving["amount"]) == Decimal("250.00")
    assert "100" in driving["working"]
    assert "2.5" in driving["working"]


def test_the_margin_is_what_came_in_less_what_went_out(client, scene, auth):
    """2,687 in, 250 driving plus 84 unloading out."""
    e = _economics(client, auth, scene)

    assert Decimal(e["revenue_total"]) == Decimal("2687.00")
    assert Decimal(e["cost_total"]) == Decimal("334.00")
    assert Decimal(e["margin"]) == Decimal("2353.00")
    assert Decimal(e["margin_per_km"]) == Decimal("23.53")


def test_an_approved_road_expense_comes_off_the_margin(client, scene, auth):
    """A trip that looks profitable until you add the diesel is not a number."""
    from app.db.session import SessionLocal
    from app.models.enums import ApprovalStatus, EntryMode, ExpenseType, PaidBy
    from app.models.expense import TripExpense

    db = SessionLocal()
    try:
        db.add(
            TripExpense(
                freight_id=scene["freight"],
                type=ExpenseType.FUEL,
                amount=Decimal("1200"),
                paid_by=PaidBy.DRIVER,
                entry_mode=EntryMode.SELF,
                approval_status=ApprovalStatus.APPROVED,
            )
        )
        db.commit()
    finally:
        db.close()

    e = _economics(client, auth, scene)
    assert Decimal(e["cost_total"]) == Decimal("1534.00")
    assert Decimal(e["margin"]) == Decimal("1153.00")


def test_a_pending_expense_is_not_yet_a_cost(client, scene, auth):
    """Nobody has decided it. Counting it would report a loss nobody agreed."""
    from app.db.session import SessionLocal
    from app.models.enums import ApprovalStatus, EntryMode, ExpenseType, PaidBy
    from app.models.expense import TripExpense

    db = SessionLocal()
    try:
        db.add(
            TripExpense(
                freight_id=scene["freight"],
                type=ExpenseType.FUEL,
                amount=Decimal("1200"),
                paid_by=PaidBy.DRIVER,
                entry_mode=EntryMode.SELF,
                approval_status=ApprovalStatus.PENDING,
            )
        )
        db.commit()
    finally:
        db.close()

    assert Decimal(_economics(client, auth, scene)["cost_total"]) == Decimal("334.00")


def test_unloading_is_not_charged_to_the_trip_twice(client, scene, auth):
    """The delivery form writes an expense for the same cash the payout pays.

    Counting both would take 84 off this trip twice, and the trips that earn
    the most unloading would look like the ones losing money.
    """
    from app.db.session import SessionLocal
    from app.models.enums import ApprovalStatus, EntryMode, ExpenseType, PaidBy
    from app.models.expense import TripExpense

    db = SessionLocal()
    try:
        db.add(
            TripExpense(
                freight_id=scene["freight"],
                freight_point_id=scene["point"],
                type=ExpenseType.UNLOADING,
                amount=Decimal("84"),
                paid_by=PaidBy.DRIVER,
                entry_mode=EntryMode.SELF,
                approval_status=ApprovalStatus.APPROVED,
            )
        )
        db.commit()
    finally:
        db.close()

    assert Decimal(_economics(client, auth, scene)["cost_total"]) == Decimal("334.00")


def test_the_trip_names_its_vehicle_and_its_driver(client, scene, auth):
    e = _economics(client, auth, scene)
    assert e["vehicle_no"] == "KL07CW3317"
    assert e["vehicle_type_name"] == "DOST"
    assert e["driver_name"] == "Suresh"
    assert e["km"] == 100
    assert e["is_settled"] is False


# ---------------------------------------------------------------------------
# The driver's own view of the same trip
# ---------------------------------------------------------------------------


@pytest.fixture()
def driver_token(client, scene):
    """A login for Suresh, allowed to see what he earns."""
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.fleet import Driver
    from app.models.user import User

    db = SessionLocal()
    try:
        user = User(
            full_name="Suresh",
            phone="9000000032",
            role=UserRole.DRIVER,
            hashed_password=hash_password("x"),
            is_active=True,
            can_view_earnings=True,
        )
        db.add(user)
        db.flush()
        db.get(Driver, scene["driver"]).user_id = user.id
        db.commit()
        return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}
    finally:
        db.close()


def test_a_driver_sees_his_rate_his_distance_and_his_unloading(
    client, scene, driver_token
):
    """The three things he can check, and their sum."""
    res = client.get(
        f"/api/driver/freights/{scene['freight']}/earnings", headers=driver_token
    )
    assert res.status_code == 200, res.text

    out = res.json()
    assert out["trip_no"] == "Y26009001"
    assert out["km"] == 100
    assert Decimal(out["total"]) == Decimal("334.00")

    driving = next(line for line in out["lines"] if line["label"] == "Driving")
    assert Decimal(driving["amount"]) == Decimal("250.00")
    assert "100" in driving["working"]

    unloading = next(line for line in out["lines"] if line["label"] == "Unloading")
    assert Decimal(unloading["amount"]) == Decimal("84.00")


def test_his_total_is_the_offices_cost_line(client, scene, auth, driver_token):
    """One number, not two screens' opinions of it."""
    his = client.get(
        f"/api/driver/freights/{scene['freight']}/earnings", headers=driver_token
    ).json()
    office = _economics(client, auth, scene)

    assert Decimal(his["total"]) == Decimal(office["cost_total"])


def test_he_is_told_nothing_about_what_the_vendor_was_charged(
    client, scene, driver_token
):
    """Not his business, and showing it starts an argument in a lorry bay."""
    body = client.get(
        f"/api/driver/freights/{scene['freight']}/earnings", headers=driver_token
    ).text

    assert "2687" not in body
    assert "1867" not in body


def test_a_driver_cannot_read_a_trip_he_did_not_drive(client, scene, driver_token):
    from app.db.session import SessionLocal
    from app.models.enums import FreightStatus
    from app.models.freight import Freight

    db = SessionLocal()
    try:
        first = db.get(Freight, scene["freight"])
        other = Freight(
            trip_no="Y26009002",
            trip_date=TRIP_DAY,
            vendor_division_id=first.vendor_division_id,
            warehouse_id=first.warehouse_id,
            status=FreightStatus.COMPLETED,
            point_count=1,
            total_km=50,
        )
        db.add(other)
        db.commit()
        other_id = str(other.id)
    finally:
        db.close()

    res = client.get(f"/api/driver/freights/{other_id}/earnings", headers=driver_token)
    assert res.status_code == 404


def test_a_driver_on_a_rented_lorry_is_refused_rather_than_shown_zero(
    client, scene, driver_token
):
    """He is paid by the vehicle's owner. An empty total reads as a missing
    payment, which starts the wrong conversation."""
    from app.db.session import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.execute(
            __import__("sqlalchemy").select(User).where(User.phone == "9000000032")
        ).scalars().first()
        user.can_view_earnings = False
        db.commit()
    finally:
        db.close()

    res = client.get(
        f"/api/driver/freights/{scene['freight']}/earnings", headers=driver_token
    )
    assert res.status_code == 403
