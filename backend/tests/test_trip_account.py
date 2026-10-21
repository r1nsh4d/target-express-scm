"""What a trip pays out, and to whom — the panel that never once loaded.

`GET /freights/{id}/account` has returned a 500 on every call since it was
written. `services.settlement.trip_accounts` reads `row.driver.name` and
`row.vehicle.owner`, and `FreightPayout` had neither relationship, so the
request died on an AttributeError before it produced a line.

It is the block on the trip screen that says what the run owes the driver or
the vehicle's owner, less any advance. Nobody noticed because the payout
ARITHMETIC is tested hard, as a pure function, and the code that assembles it
for a screen was not tested at all. A function that cannot run is not caught
by testing the function it calls.

So these go through the endpoint. The shapes they hold:

  * A RENTED TRIP PAYS TWO PARTIES. The hire settles to the vehicle's owner
    and the unloading cash goes to the driver who handed it over, from one
    leg — so one trip produces two accounts, and a screen showing one of them
    is a screen that underpays somebody.
  * THE DRIVER IS NAMED EITHER WAY. The settlement document names the man who
    drove it even when the money goes to his owner.
  * AN ADVANCE COMES OFF THE BALANCE, not off the gross. What was earned and
    what is left to pay are two different numbers and both are on the screen.
"""

from __future__ import annotations

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
    "point_unloading_items",
    "consignments",
    "boxes",
    "freight_points",
    "freight_legs",
    "trip_expenses",
    "settlements",
    "freight_payouts",
    "advances",
)

TODAY = date.today()
TRIP_DAY = TODAY - timedelta(days=2)


@pytest.fixture()
def rented_run(client, auth):
    """A rented lorry: the hire is the owner's, the unloading is the driver's."""
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee
    from app.models.enums import (
        ChargeHead,
        ConsigneeType,
        FreightStatus,
        GeoConfidence,
        PayeeType,
        VehicleOwnership,
    )
    from app.models.fleet import Driver, Vehicle, VehicleHireTerms, VehicleOwner
    from app.models.freight import Freight, FreightLeg, FreightPoint
    from app.models.settlement import FreightPayout
    from app.models.vendor import Vendor, VendorDivision, VendorWarehouse

    db = SessionLocal()

    vendor = Vendor(name="Godrej", is_active=True)
    db.add(vendor)
    db.flush()
    division = VendorDivision(
        vendor_id=vendor.id, name="OCP", code="OCP", invoice_series="191", is_active=True
    )
    warehouse = VendorWarehouse(vendor_id=vendor.id, name="Kochi", code="KOCHI")
    owner = VehicleOwner(name="Shaji", phone="9000000801", is_active=True)
    db.add_all([division, warehouse, owner])
    db.flush()

    lorry = Vehicle(
        owner_id=owner.id,
        registration_no="KL10AL4477",
        ownership=VehicleOwnership.HIRED,
        lr_next_number=1,
        is_active=True,
    )
    driver = Driver(name="Basheer C", phone="9000000802", is_active=True)
    consignee = Consignee(
        name="Aluva Dealer",
        type=ConsigneeType.RETAIL_CUSTOMER,
        city="Aluva",
        geo_confidence=GeoConfidence.UNVERIFIED,
    )
    db.add_all([lorry, driver, consignee])
    db.flush()

    freight = Freight(
        trip_no="Y26011001",
        trip_date=TRIP_DAY,
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.COMPLETED,
        point_count=1,
        total_km=100,
    )
    db.add(freight)
    db.flush()
    db.add(FreightPoint(freight_id=freight.id, sequence=1, consignee_id=consignee.id))
    leg = FreightLeg(
        freight_id=freight.id,
        sequence=1,
        vehicle_id=lorry.id,
        driver_id=driver.id,
        start_odometer=1000,
        end_odometer=1100,
        leg_distance_km=100,
    )
    db.add(leg)
    db.flush()

    # The terms the hire is worked out from: 13 a kilometre, so a 100 km run
    # is 1,300. Written down rather than assumed, so a recompute produces the
    # same figures the hand-made rows below do.
    db.add(
        VehicleHireTerms(
            vehicle_id=lorry.id,
            rate_value=Decimal("13"),
            minimum_km_per_trip=0,
            effective_from=TRIP_DAY - timedelta(days=30),
        )
    )
    # And the unloading cash that actually left somebody's pocket at the door.
    db.execute(
        __import__("sqlalchemy").update(FreightPoint)
        .where(FreightPoint.freight_id == freight.id)
        .values(unloading_paid=Decimal("240"))
    )

    # The hire, to the owner.
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
    # The unloading cash, to the man who handed it over.
    db.add(
        FreightPayout(
            freight_id=freight.id,
            leg_id=leg.id,
            head=ChargeHead.LOADING_UNLOADING,
            payee_type=PayeeType.DRIVER,
            driver_id=driver.id,
            vehicle_id=lorry.id,
            amount=Decimal("240"),
        )
    )
    db.commit()

    data = {
        "freight": str(freight.id),
        "driver": str(driver.id),
        "owner": str(owner.id),
    }
    db.close()
    return data


def _account(client, auth, run):
    res = client.get(f"/api/freights/{run['freight']}/account", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# That it runs at all
# ---------------------------------------------------------------------------


def test_the_panel_loads(client, rented_run, auth):
    """It has returned 500 on every call since it was written."""
    rows = _account(client, auth, rented_run)
    assert rows


def test_a_rented_trip_pays_two_parties(client, rented_run, auth):
    """The hire settles to the owner and the unloading goes to the driver,
    from one leg. A screen showing one of them underpays somebody."""
    rows = _account(client, auth, rented_run)

    payees = {r["payee_type"]: r for r in rows}
    assert set(payees) == {"VEHICLE_OWNER", "DRIVER"}
    assert Decimal(payees["VEHICLE_OWNER"]["gross"]) == Decimal("1300.00")
    assert Decimal(payees["DRIVER"]["gross"]) == Decimal("240.00")


def test_the_parties_are_named(client, rented_run, auth):
    """This is the line that raised the AttributeError."""
    rows = _account(client, auth, rented_run)
    by_type = {r["payee_type"]: r for r in rows}

    assert by_type["VEHICLE_OWNER"]["payee_name"] == "Shaji"
    assert by_type["DRIVER"]["payee_name"] == "Basheer C"


def test_the_driver_is_named_even_when_the_money_is_not_his(
    client, rented_run, auth
):
    """The settlement document names the man who drove it either way."""
    rows = _account(client, auth, rented_run)
    owner_row = next(r for r in rows if r["payee_type"] == "VEHICLE_OWNER")

    assert "Basheer C" in owner_row["driver_names"]


def test_the_heads_are_split_out(client, rented_run, auth):
    rows = _account(client, auth, rented_run)
    driver_row = next(r for r in rows if r["payee_type"] == "DRIVER")

    assert Decimal(driver_row["by_head"]["LOADING_UNLOADING"]) == Decimal("240.00")


# ---------------------------------------------------------------------------
# Advances, which are the reason the panel exists
# ---------------------------------------------------------------------------


def _advance(run, amount: str, recovered: str) -> None:
    from decimal import Decimal as D

    from app.db.session import SessionLocal
    from app.models.enums import PayeeType
    from app.models.settlement import Advance

    db = SessionLocal()
    try:
        db.add(
            Advance(
                payee_type=PayeeType.VEHICLE_OWNER,
                vehicle_owner_id=run["owner"],
                freight_id=run["freight"],
                advance_date=TRIP_DAY,
                amount=D(amount),
                recovered_amount=D(recovered),
                reason="Diesel",
            )
        )
        db.commit()
    finally:
        db.close()


def _owner_row(client, auth, run):
    return next(
        r for r in _account(client, auth, run) if r["payee_type"] == "VEHICLE_OWNER"
    )


def test_drawing_an_advance_does_not_by_itself_reduce_what_is_payable(
    client, rented_run, auth
):
    """Drawn and recovered are different events.

    Cash handed over on Tuesday is shown against the trip immediately — the
    office needs to see it — but it comes off what is payable when it is
    actually recovered at settlement. Deducting it the moment it is drawn
    would show a man as already paid for work nobody has settled.
    """
    _advance(rented_run, "500", "0")
    row = _owner_row(client, auth, rented_run)

    assert Decimal(row["gross"]) == Decimal("1300.00")
    assert Decimal(row["advance_drawn"]) == Decimal("500.00")
    assert Decimal(row["balance_payable"]) == Decimal("1300.00")
    assert Decimal(row["advance_carried_forward"]) == Decimal("500.00")


def test_a_recovered_advance_comes_off_what_is_payable(client, rented_run, auth):
    """1,300 earned, 500 already in his pocket, 800 to hand over."""
    _advance(rented_run, "500", "500")
    row = _owner_row(client, auth, rented_run)

    assert Decimal(row["gross"]) == Decimal("1300.00")
    assert Decimal(row["balance_payable"]) == Decimal("800.00")
    assert Decimal(row["advance_carried_forward"]) == Decimal("0.00")
    assert row["is_closed"] is False


def test_an_advance_the_trip_cannot_absorb_carries_forward(client, rented_run, auth):
    """2,000 drawn against a 1,300 run: the rest comes off the next one."""
    _advance(rented_run, "2000", "1300")
    row = _owner_row(client, auth, rented_run)

    assert Decimal(row["balance_payable"]) == Decimal("0.00")
    assert Decimal(row["advance_carried_forward"]) == Decimal("700.00")
    assert row["is_closed"] is True


def test_a_freight_with_no_payouts_yet_is_an_empty_list(client, rented_run, auth):
    """A trip that has not closed owes nobody anything yet, and that is an
    answer rather than an error."""
    from sqlalchemy import delete

    from app.db.session import SessionLocal
    from app.models.settlement import FreightPayout

    db = SessionLocal()
    try:
        db.execute(delete(FreightPayout))
        db.commit()
    finally:
        db.close()

    assert _account(client, auth, rented_run) == []


# ---------------------------------------------------------------------------
# When the owner is the man driving it
# ---------------------------------------------------------------------------

"""One man, one run, one settlement.

Most of the hired fleet is owner-driven. The hire settles to the owner and the
unloading cash to the driver who handed it over — two payout rows to two
payees, which when both are the same man is two settlements for one person's
work on one trip. He rings to ask why he was paid twice, or worse, does not
ring and assumes one of them is missing.

So where the driver IS the owner, the unloading follows the hire to him.
Nothing about what he is OWED changes; what changes is that it arrives as one
settlement he can read rather than two he has to add up.
"""


def _make_owner_driver(run) -> None:
    """Link the driver's login to the owner of the lorry he is driving."""
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.fleet import Driver
    from app.models.user import User

    db = SessionLocal()
    try:
        user = User(
            full_name="Shaji",
            phone="9000000901",
            role=UserRole.OWNER_DRIVER,
            hashed_password=hash_password("x"),
            is_active=True,
            vehicle_owner_id=run["owner"],
        )
        db.add(user)
        db.flush()
        db.get(Driver, run["driver"]).user_id = user.id
        db.commit()
    finally:
        db.close()


def _repay(run) -> None:
    """Re-run the payout, as closing the leg does."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.freight import FreightLeg
    from app.services.completion import record_leg_payouts

    db = SessionLocal()
    try:
        leg = db.execute(
            select(FreightLeg).where(FreightLeg.freight_id == run["freight"])
        ).scalars().first()
        record_leg_payouts(db, leg)
        db.commit()
    finally:
        db.close()


def test_an_owner_driver_is_paid_once(client, rented_run, auth):
    """Both halves are his, so they arrive as one account rather than two."""
    _make_owner_driver(rented_run)
    _repay(rented_run)

    rows = _account(client, auth, rented_run)

    assert [r["payee_type"] for r in rows] == ["VEHICLE_OWNER"]
    assert rows[0]["payee_name"] == "Shaji"


def test_he_is_not_paid_any_less_for_it(client, rented_run, auth):
    """The split was presentational. What he is owed does not move."""
    _make_owner_driver(rented_run)
    _repay(rented_run)

    row = _account(client, auth, rented_run)[0]
    # The hire plus the unloading he handed over, as before.
    assert Decimal(row["gross"]) > Decimal("1300.00")


def test_a_hired_driver_on_the_same_lorry_is_still_paid_separately(
    client, rented_run, auth
):
    """The ordinary case is untouched: a man driving somebody else's lorry
    gets the unloading and the owner gets the hire."""
    _repay(rented_run)

    rows = _account(client, auth, rented_run)
    assert {r["payee_type"] for r in rows} == {"VEHICLE_OWNER", "DRIVER"}


def test_driving_a_lorry_he_does_not_own_changes_nothing(client, rented_run, auth):
    """Being an owner somewhere is not the same as owning THIS one."""
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.fleet import Driver, VehicleOwner
    from app.models.user import User

    db = SessionLocal()
    try:
        other = VehicleOwner(name="Basheer", phone="9000000902", is_active=True)
        db.add(other)
        db.flush()
        user = User(
            full_name="Basheer",
            phone="9000000902",
            role=UserRole.OWNER_DRIVER,
            hashed_password=hash_password("x"),
            is_active=True,
            vehicle_owner_id=other.id,
        )
        db.add(user)
        db.flush()
        db.get(Driver, rented_run["driver"]).user_id = user.id
        db.commit()
    finally:
        db.close()

    _repay(rented_run)

    rows = _account(client, auth, rented_run)
    assert {r["payee_type"] for r in rows} == {"VEHICLE_OWNER", "DRIVER"}
