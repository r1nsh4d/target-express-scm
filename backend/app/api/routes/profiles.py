"""One lorry, or one driver, with everything about it in one place.

The masters list answers "which vehicles do we have". It cannot answer the
question people actually ask, which is about one of them: how much has this
lorry run, what did it earn, who drives it, is its odometer chain intact — or,
for a driver, what has he run, what is he owed, what has he already been paid
and what is outstanding against him in advances.

Until now that meant three screens and a period report, and the answer came
out different depending on which one you looked at. This assembles it from the
same documents the reports use, so it cannot disagree with them.

A LORRY'S COST AND A DRIVER'S PAY ARE NOT THE SAME MONEY
    An owned vehicle pays its driver; a rented one pays the vehicle's owner.
    A driver's earnings here are his payout rows, whoever the vehicle belongs
    to; a vehicle's cost is every payout against it, to whoever received it.
    The same trip appears in both and the figures are deliberately different.

INVOICED, NOT RECEIVED
    What a lorry earned is what the vendor was invoiced for its trips. Whether
    the vendor has paid is a question about the vendor, not about the lorry.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import BACK_OFFICE_ROLES, require_capability, require_roles
from app.core.privileges import Capability
from app.db.session import get_db
from app.models.billing import VendorInvoiceLine
from app.models.enums import AdvanceStatus, PayeeType
from app.models.fleet import Driver, Vehicle, VehicleHireTerms, VehicleOwner, VehicleType
from app.models.freight import Freight, FreightLeg
from app.models.settlement import Advance, FreightPayout, Settlement
from app.services.economics import freight_economics
from app.services.rating import money

router = APIRouter(prefix="/api", tags=["profiles"])

ReadDep = Depends(require_roles(*BACK_OFFICE_ROLES))

ZERO = Decimal("0.00")


class RunRow(BaseModel):
    """One trip, as it looks from the vehicle or the driver that ran it."""

    freight_id: str
    trip_no: str
    lr_no: str | None
    trip_date: date
    status: str
    destination_text: str | None
    point_count: int
    km: int
    # Who the other half was: the driver on a vehicle's row, the vehicle on a
    # driver's row.
    counterpart: str | None
    # What the vendor was invoiced for this trip, if it has been invoiced.
    invoiced: Decimal | None
    # What this trip paid out to the party being looked at.
    paid: Decimal


class VehicleProfileOut(BaseModel):
    id: str
    registration_no: str
    vehicle_type_name: str | None
    ownership: str
    owner_name: str | None
    is_active: bool

    lr_prefix: str | None
    lr_next_number: int
    last_closing_km: int | None

    # The papers. A lorry with an expired fitness certificate is one that
    # should not be assigned tomorrow, and the only place that was visible
    # was a column nobody had put on the list.
    insurance_expiry: date | None
    fitness_expiry: date | None
    permit_expiry: date | None
    puc_expiry: date | None
    expired_papers: list[str]

    # Rented vehicles only, from the hire terms in force today.
    hire_rate_basis: str | None
    hire_rate_value: Decimal | None
    hire_minimum_km: int
    hire_includes_unloading: bool

    trips: int
    km: int
    invoiced: Decimal
    cost: Decimal
    margin: Decimal
    # The figure that decides whether to buy another one or stop hiring this
    # one. A DOST on short town runs and a lorry doing Kasaragod and back
    # cannot be compared any other way.
    margin_per_km: Decimal

    first_trip: date | None
    last_trip: date | None
    drivers: list[str]
    runs: list[RunRow]


class SettlementRow(BaseModel):
    id: str
    settlement_no: str
    settlement_date: date
    period_from: date
    period_to: date
    trip_count: int
    gross_amount: Decimal
    advance_recovered: Decimal
    net_payable: Decimal
    status: str


class AdvanceRow(BaseModel):
    id: str
    advance_date: date
    amount: Decimal
    recovered_amount: Decimal
    outstanding: Decimal
    reason: str | None
    status: str


class DriverProfileOut(BaseModel):
    id: str
    name: str
    phone: str
    engagement: str
    # Whose man he is. Null is a Target Express driver, paid by us; set, and
    # he belongs to that owner, who pays him out of what we pay for the
    # lorry. "On a rented vehicle" is not the answer anybody wants — the
    # question is whose.
    vehicle_owner_name: str | None = None
    licence_no: str | None
    is_active: bool
    has_login: bool

    trips: int
    km: int
    points: int

    # What he has earned, and where it stands. Earned is every payout row with
    # his name on it; settled is the part already covered by a settlement;
    # unsettled is the rest, which is what he is owed right now.
    earned: Decimal
    settled: Decimal
    unsettled: Decimal
    # By head, because "why is this less than last month" is nearly always one
    # head rather than the total.
    transportation: Decimal
    unloading: Decimal
    point_incentive: Decimal
    other: Decimal

    advances_outstanding: Decimal

    first_trip: date | None
    last_trip: date | None
    vehicles: list[str]
    runs: list[RunRow]
    settlements: list[SettlementRow]
    advances: list[AdvanceRow]


def _invoiced_by_freight(db: Session, freight_ids: list) -> dict:
    """What each of these freights was invoiced for, if anything."""
    if not freight_ids:
        return {}
    rows = db.execute(
        select(VendorInvoiceLine.freight_id, VendorInvoiceLine.line_total).where(
            VendorInvoiceLine.freight_id.in_(freight_ids)
        )
    ).all()
    return {row[0]: Decimal(row[1]) for row in rows}


class MoneyLineOut(BaseModel):
    label: str
    amount: Decimal
    working: str


class UnloadingPointOut(BaseModel):
    point_id: str
    sequence: int
    customer_name: str
    floor_number: int
    has_lift: bool
    articles: list[dict]
    charged: Decimal
    driver_pay: Decimal
    margin: Decimal


class EconomicsOut(BaseModel):
    trip_no: str
    trip_date: str
    status: str
    vehicle_no: str | None
    vehicle_type_name: str | None
    driver_name: str | None
    km: int
    points: int
    revenue: list[MoneyLineOut]
    revenue_total: Decimal
    revenue_problem: str | None
    cost: list[MoneyLineOut]
    cost_total: Decimal
    paid_to: str
    is_settled: bool
    unloading_points: list[UnloadingPointOut]
    margin: Decimal
    margin_percent: Decimal
    margin_per_km: Decimal


@router.get("/freights/{freight_id}/economics", response_model=EconomicsOut)
def freight_money(
    freight_id: str,
    db: Session = Depends(get_db),
    # What the vendor was charged and what the trip made. Not the warehouse's
    # business — it builds freights, it does not price them — so this is
    # behind the same capability as the reports rather than behind
    # `office.view`, which everybody in the office has.
    _=Depends(require_capability(Capability.REPORTS)),
):
    """In, out, and what is left — for one trip.

    The office's view of the question the driver asks about his own pay. Both
    come off `services.economics`, so his total and the cost line here are the
    same number rather than two screens' opinions of it.
    """
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise HTTPException(status_code=404, detail="Freight not found")

    e = freight_economics(db, freight)
    return EconomicsOut(
        **{
            **e.__dict__,
            "revenue": [MoneyLineOut(**line.__dict__) for line in e.revenue],
            "cost": [MoneyLineOut(**line.__dict__) for line in e.cost],
            "unloading_points": [
                UnloadingPointOut(**{**p.__dict__, "margin": p.margin})
                for p in e.unloading_points
            ],
            "margin": e.margin,
            "margin_percent": e.margin_percent,
            "margin_per_km": e.margin_per_km,
        }
    )


@router.get("/vehicles/{vehicle_id}/profile", response_model=VehicleProfileOut)
def vehicle_profile(vehicle_id: str, db: Session = Depends(get_db), _=ReadDep):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    vehicle_type = (
        db.get(VehicleType, vehicle.vehicle_type_id) if vehicle.vehicle_type_id else None
    )
    owner = db.get(VehicleOwner, vehicle.owner_id) if vehicle.owner_id else None

    today = date.today()
    expired = [
        label
        for label, when in (
            ("Insurance", vehicle.insurance_expiry),
            ("Fitness", vehicle.fitness_expiry),
            ("Permit", vehicle.permit_expiry),
            ("PUC", vehicle.puc_expiry),
        )
        if when is not None and when < today
    ]

    # The terms in force now, not every version ever agreed. A rented lorry
    # with no current terms is a real state — somebody added the vehicle and
    # stopped — and it reads as "no rate set" rather than as zero.
    terms = (
        db.execute(
            select(VehicleHireTerms)
            .where(
                VehicleHireTerms.vehicle_id == vehicle.id,
                VehicleHireTerms.effective_from <= today,
            )
            .order_by(VehicleHireTerms.effective_from.desc())
        )
        .scalars()
        .first()
    )

    # Through the legs, not the freight: a breakdown splits a trip across two
    # vehicles, and each one did only its own share of the kilometres.
    legs = (
        db.execute(
            select(FreightLeg, Freight, Driver)
            .join(Freight, Freight.id == FreightLeg.freight_id)
            .join(Driver, Driver.id == FreightLeg.driver_id)
            .where(FreightLeg.vehicle_id == vehicle.id)
            .order_by(Freight.trip_date.desc(), Freight.trip_no.desc())
        )
        .unique()
        .all()
    )

    freight_ids = [freight.id for _, freight, _ in legs]
    invoiced_by = _invoiced_by_freight(db, freight_ids)

    # Every payout against this vehicle, to whoever received it — the driver on
    # an owned lorry, the owner on a rented one.
    paid_by_freight: dict = {}
    for freight_id, amount in db.execute(
        select(FreightPayout.freight_id, func.sum(FreightPayout.amount))
        .where(FreightPayout.vehicle_id == vehicle.id)
        .group_by(FreightPayout.freight_id)
    ).all():
        paid_by_freight[freight_id] = Decimal(amount or 0)

    runs: list[RunRow] = []
    seen_invoice: set = set()
    total_km = 0
    total_invoiced = ZERO
    total_cost = ZERO
    drivers: list[str] = []

    for leg, freight, driver in legs:
        km = int(leg.leg_distance_km or 0)
        total_km += km

        # An invoice line is per freight, not per leg. On a two-leg trip it
        # must not be counted twice against the same vehicle.
        line_total = invoiced_by.get(freight.id)
        if line_total is not None and freight.id not in seen_invoice:
            total_invoiced += line_total
            seen_invoice.add(freight.id)

        paid = paid_by_freight.get(freight.id, ZERO)
        total_cost += paid

        if driver.name not in drivers:
            drivers.append(driver.name)

        runs.append(
            RunRow(
                freight_id=str(freight.id),
                trip_no=freight.trip_no,
                lr_no=freight.lr_no,
                trip_date=freight.trip_date,
                status=str(freight.status),
                destination_text=freight.destination_text,
                point_count=freight.point_count,
                km=km,
                counterpart=driver.name,
                invoiced=line_total,
                paid=money(paid),
            )
        )

    dates = [freight.trip_date for _, freight, _ in legs]
    margin = money(total_invoiced - total_cost)

    return VehicleProfileOut(
        id=str(vehicle.id),
        registration_no=vehicle.registration_no,
        vehicle_type_name=vehicle_type.name if vehicle_type else None,
        ownership=str(vehicle.ownership),
        owner_name=owner.name if owner else None,
        is_active=vehicle.is_active,
        lr_prefix=vehicle.lr_prefix,
        lr_next_number=vehicle.lr_next_number,
        last_closing_km=vehicle.last_closing_km,
        insurance_expiry=vehicle.insurance_expiry,
        fitness_expiry=vehicle.fitness_expiry,
        permit_expiry=vehicle.permit_expiry,
        puc_expiry=vehicle.puc_expiry,
        expired_papers=expired,
        hire_rate_basis=str(terms.rate_basis) if terms else None,
        hire_rate_value=terms.rate_value if terms else None,
        hire_minimum_km=terms.minimum_km_per_trip if terms else 0,
        hire_includes_unloading=bool(terms.includes_unloading) if terms else False,
        trips=len({freight.id for _, freight, _ in legs}),
        km=total_km,
        invoiced=money(total_invoiced),
        cost=money(total_cost),
        margin=margin,
        margin_per_km=money(margin / Decimal(total_km)) if total_km else ZERO,
        first_trip=min(dates) if dates else None,
        last_trip=max(dates) if dates else None,
        drivers=drivers,
        runs=runs,
    )


@router.get("/drivers/{driver_id}/profile", response_model=DriverProfileOut)
def driver_profile(driver_id: str, db: Session = Depends(get_db), _=ReadDep):
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(status_code=404, detail="Driver not found")

    legs = (
        db.execute(
            select(FreightLeg, Freight, Vehicle)
            .join(Freight, Freight.id == FreightLeg.freight_id)
            .join(Vehicle, Vehicle.id == FreightLeg.vehicle_id)
            .where(FreightLeg.driver_id == driver.id)
            .order_by(Freight.trip_date.desc(), Freight.trip_no.desc())
        )
        .unique()
        .all()
    )

    freight_ids = [freight.id for _, freight, _ in legs]
    invoiced_by = _invoiced_by_freight(db, freight_ids)

    # His payouts, by freight and by head. Rows where the money went to a
    # vehicle owner are not his, even though his name is on them — the model
    # records the driver on every row so the document can name him.
    payouts = (
        db.execute(
            select(FreightPayout).where(
                FreightPayout.driver_id == driver.id,
                FreightPayout.payee_type == PayeeType.DRIVER,
            )
        )
        .scalars()
        .all()
    )

    by_head: dict[str, Decimal] = {}
    paid_by_freight: dict = {}
    earned = ZERO
    settled = ZERO
    for payout in payouts:
        amount = Decimal(payout.amount)
        earned += amount
        head = str(payout.head)
        by_head[head] = by_head.get(head, ZERO) + amount
        paid_by_freight[payout.freight_id] = paid_by_freight.get(payout.freight_id, ZERO) + amount
        if payout.settlement_id is not None:
            settled += amount

    runs: list[RunRow] = []
    total_km = 0
    total_points = 0
    vehicles: list[str] = []
    for leg, freight, vehicle in legs:
        km = int(leg.leg_distance_km or 0)
        total_km += km
        total_points += freight.point_count
        if vehicle.registration_no not in vehicles:
            vehicles.append(vehicle.registration_no)
        runs.append(
            RunRow(
                freight_id=str(freight.id),
                trip_no=freight.trip_no,
                lr_no=freight.lr_no,
                trip_date=freight.trip_date,
                status=str(freight.status),
                destination_text=freight.destination_text,
                point_count=freight.point_count,
                km=km,
                counterpart=vehicle.registration_no,
                invoiced=invoiced_by.get(freight.id),
                paid=money(paid_by_freight.get(freight.id, ZERO)),
            )
        )

    settlements = (
        db.execute(
            select(Settlement)
            .where(
                Settlement.driver_id == driver.id,
                Settlement.payee_type == PayeeType.DRIVER,
            )
            .order_by(Settlement.settlement_date.desc())
        )
        .scalars()
        .all()
    )

    advances = (
        db.execute(
            select(Advance)
            .where(Advance.driver_id == driver.id)
            .order_by(Advance.advance_date.desc())
        )
        .scalars()
        .all()
    )

    dates = [freight.trip_date for _, freight, _ in legs]

    owner = (
        db.get(VehicleOwner, driver.vehicle_owner_id)
        if driver.vehicle_owner_id is not None
        else None
    )

    return DriverProfileOut(
        id=str(driver.id),
        name=driver.name,
        phone=driver.phone,
        engagement=str(driver.engagement),
        vehicle_owner_name=owner.name if owner else None,
        licence_no=driver.licence_no,
        is_active=driver.is_active,
        has_login=driver.user_id is not None,
        trips=len({freight.id for _, freight, _ in legs}),
        km=total_km,
        points=total_points,
        earned=money(earned),
        settled=money(settled),
        unsettled=money(earned - settled),
        transportation=money(by_head.get("TRANSPORTATION", ZERO)),
        unloading=money(by_head.get("LOADING_UNLOADING", ZERO)),
        point_incentive=money(by_head.get("POINT_INCENTIVE", ZERO)),
        other=money(
            sum(
                (
                    amount
                    for head, amount in by_head.items()
                    if head
                    not in ("TRANSPORTATION", "LOADING_UNLOADING", "POINT_INCENTIVE")
                ),
                ZERO,
            )
        ),
        advances_outstanding=money(
            sum(
                (a.outstanding for a in advances if a.status == AdvanceStatus.OUTSTANDING),
                ZERO,
            )
        ),
        first_trip=min(dates) if dates else None,
        last_trip=max(dates) if dates else None,
        vehicles=vehicles,
        runs=runs,
        settlements=[
            SettlementRow(
                id=str(s.id),
                settlement_no=s.settlement_no,
                settlement_date=s.settlement_date,
                period_from=s.period_from,
                period_to=s.period_to,
                trip_count=s.trip_count,
                gross_amount=s.gross_amount,
                advance_recovered=s.advance_recovered,
                net_payable=s.net_payable,
                status=str(s.status),
            )
            for s in settlements
        ],
        advances=[
            AdvanceRow(
                id=str(a.id),
                advance_date=a.advance_date,
                amount=a.amount,
                recovered_amount=a.recovered_amount,
                outstanding=a.outstanding,
                reason=a.reason,
                status=str(a.status),
            )
            for a in advances
        ],
    )
