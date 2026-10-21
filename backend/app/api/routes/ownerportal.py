"""What a hired lorry earned, for the man who owns it.

A rented vehicle is settled to its OWNER, who pays his own driver. So the
money question belongs to him and not to the man at the wheel — which is
exactly why a driver on a rented lorry has his earnings screen switched off
and has nothing to put in its place. He runs the trip; his owner is paid for
it; and until now the owner found out how much by ringing the office at the
end of the month.

ONE RULE, AS WITH THE VENDOR PORTAL

An owner login is tied to one vehicle owner and every query filters on it. He
sees his own lorries, his own drivers' runs, his own settlements and his own
advances. Nothing about what the vendor was charged appears anywhere: the gap
between what Godrej pays and what he is paid is Target Express's margin, and
handing a contractor both halves of it is handing him a negotiation.

WHAT HE SEES THAT THE DRIVER DOES NOT

Per-run earnings, settlements and the advances drawn against them. The driver
on that same lorry sees the run and the stops and nothing else — the earnings
tab is not shown to him at all, because the money is not his.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_capability
from app.core.privileges import Capability
from app.db.session import get_db
from app.models.enums import AdvanceStatus, PayeeType
from app.models.fleet import Vehicle, VehicleOwner
from app.models.freight import Freight, FreightLeg
from app.models.settlement import Advance, FreightPayout, Settlement
from app.models.user import User
from app.services.rating import money

router = APIRouter(prefix="/api/owner", tags=["owner portal"])

PortalDep = Depends(require_capability(Capability.OWNER_PORTAL))


def _my_owner(user: User = Depends(get_current_user)) -> str:
    """The owner this login belongs to.

    An owner login with nothing on it is a login that was made wrong, not one
    that sees every owner. Failing closed here is the difference between a
    misconfiguration and a disclosure.
    """
    from app.api.deps import capabilities_of

    if Capability.OWNER_PORTAL not in capabilities_of(user):
        raise HTTPException(status_code=403, detail="This is not a vehicle owner login")
    if user.vehicle_owner_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "This login is not linked to a vehicle owner yet. Ask Target Express "
                "to finish setting it up."
            ),
        )
    return str(user.vehicle_owner_id)


def _my_vehicles(db: Session, owner_id: str) -> list:
    return (
        db.execute(select(Vehicle).where(Vehicle.owner_id == owner_id)).scalars().all()
    )


class OwnerHomeOut(BaseModel):
    owner_name: str
    vehicles: list[dict]
    # The month, in the only terms that matter to him.
    trips_this_month: int
    km_this_month: int
    earned_this_month: Decimal
    # What has not been settled yet — the figure he is actually ringing about.
    unsettled: Decimal
    advances_outstanding: Decimal


@router.get("/home", response_model=OwnerHomeOut)
def home(db: Session = Depends(get_db), owner_id: str = Depends(_my_owner), _=PortalDep):
    owner = db.get(VehicleOwner, owner_id)
    vehicles = _my_vehicles(db, owner_id)
    vehicle_ids = [v.id for v in vehicles]

    today = date.today()
    month_start = today.replace(day=1)

    rows: list[FreightPayout] = []
    if vehicle_ids:
        rows = (
            db.execute(
                select(FreightPayout).where(
                    FreightPayout.vehicle_owner_id == owner_id,
                    FreightPayout.payee_type == PayeeType.VEHICLE_OWNER,
                )
            )
            .scalars()
            .all()
        )

    this_month = [
        r
        for r in rows
        if (f := db.get(Freight, r.freight_id)) is not None
        and month_start <= f.trip_date <= today
    ]
    earned_month = money(sum((Decimal(r.amount) for r in this_month), Decimal("0")))
    unsettled = money(
        sum(
            (Decimal(r.amount) for r in rows if r.settlement_id is None),
            Decimal("0"),
        )
    )

    km_month = int(
        db.scalar(
            select(func.coalesce(func.sum(FreightLeg.leg_distance_km), 0))
            .join(Freight, Freight.id == FreightLeg.freight_id)
            .where(
                FreightLeg.vehicle_id.in_(vehicle_ids or [None]),
                Freight.trip_date >= month_start,
                Freight.trip_date <= today,
            )
        )
        or 0
    )

    advances = (
        db.execute(
            select(Advance).where(
                Advance.vehicle_owner_id == owner_id,
                Advance.status.in_(
                    [AdvanceStatus.OUTSTANDING, AdvanceStatus.PART_RECOVERED]
                ),
            )
        )
        .scalars()
        .all()
    )

    return OwnerHomeOut(
        owner_name=owner.name if owner else "—",
        vehicles=[
            {
                "id": str(v.id),
                "registration_no": v.registration_no,
                "last_closing_km": v.last_closing_km,
                "is_active": v.is_active,
            }
            for v in vehicles
        ],
        trips_this_month=len({r.freight_id for r in this_month}),
        km_this_month=km_month,
        earned_this_month=earned_month,
        unsettled=unsettled,
        advances_outstanding=money(
            sum((a.outstanding for a in advances), Decimal("0"))
        ),
    )


class OwnerRunOut(BaseModel):
    freight_id: str
    trip_no: str
    lr_no: str | None
    trip_date: date
    vehicle_no: str
    driver_name: str | None
    destination_text: str | None
    points: int
    km: int
    earned: Decimal
    # Whether it has been paid, and on which settlement.
    settlement_no: str | None


@router.get("/runs", response_model=list[OwnerRunOut])
def my_runs(
    days: int = Query(default=60, ge=1, le=365),
    db: Session = Depends(get_db),
    owner_id: str = Depends(_my_owner),
    _=PortalDep,
):
    """Every run his lorries did, and what each one pays him.

    Run by run rather than a monthly figure, for the same reason the driver's
    screen is: a total is something to accept or argue with, and a run he
    remembers is something he can check.
    """
    since = date.today() - timedelta(days=days)

    rows = (
        db.execute(
            select(FreightPayout, Freight)
            .join(Freight, Freight.id == FreightPayout.freight_id)
            .where(
                FreightPayout.vehicle_owner_id == owner_id,
                FreightPayout.payee_type == PayeeType.VEHICLE_OWNER,
                Freight.trip_date >= since,
            )
            .order_by(Freight.trip_date.desc(), Freight.trip_no.desc())
        )
        .unique()
        .all()
    )

    by_freight: dict = {}
    for payout, freight in rows:
        key = str(freight.id)
        entry = by_freight.setdefault(
            key, {"freight": freight, "amount": Decimal("0"), "settlement": None}
        )
        entry["amount"] += Decimal(payout.amount)
        if payout.settlement_id is not None and entry["settlement"] is None:
            settlement = db.get(Settlement, payout.settlement_id)
            entry["settlement"] = settlement.settlement_no if settlement else None

    out: list[OwnerRunOut] = []
    for entry in by_freight.values():
        freight: Freight = entry["freight"]
        mine = [
            leg
            for leg in freight.legs
            if leg.vehicle is not None and str(leg.vehicle.owner_id) == owner_id
        ]
        out.append(
            OwnerRunOut(
                freight_id=str(freight.id),
                trip_no=freight.trip_no,
                lr_no=freight.lr_no,
                trip_date=freight.trip_date,
                vehicle_no=next(
                    (leg.vehicle.registration_no for leg in mine if leg.vehicle), "—"
                ),
                driver_name=next((leg.driver.name for leg in mine if leg.driver), None),
                destination_text=freight.destination_text,
                points=freight.billable_point_count,
                # His lorry's own legs. On a trip finished by a replacement,
                # the kilometres the other vehicle covered are not his.
                km=sum(leg.leg_distance_km or 0 for leg in mine),
                earned=money(entry["amount"]),
                settlement_no=entry["settlement"],
            )
        )
    return out


class OwnerSettlementOut(BaseModel):
    id: str
    settlement_no: str
    settlement_date: date
    period_from: date
    period_to: date
    trip_count: int
    total_km: int
    gross_amount: Decimal
    advance_recovered: Decimal
    deductions: Decimal
    net_payable: Decimal
    status: str
    paid_at: str | None
    payment_reference: str | None


@router.get("/settlements", response_model=list[OwnerSettlementOut])
def my_settlements(
    db: Session = Depends(get_db), owner_id: str = Depends(_my_owner), _=PortalDep
):
    """What has been paid, and what it was made up of."""
    rows = (
        db.execute(
            select(Settlement)
            .where(
                Settlement.vehicle_owner_id == owner_id,
                Settlement.payee_type == PayeeType.VEHICLE_OWNER,
            )
            .order_by(Settlement.settlement_date.desc())
        )
        .unique()
        .scalars()
        .all()
    )
    return [
        OwnerSettlementOut(
            id=str(s.id),
            settlement_no=s.settlement_no,
            settlement_date=s.settlement_date,
            period_from=s.period_from,
            period_to=s.period_to,
            trip_count=s.trip_count,
            total_km=s.total_km,
            gross_amount=s.gross_amount,
            advance_recovered=s.advance_recovered,
            deductions=s.deductions,
            net_payable=s.net_payable,
            status=str(s.status),
            paid_at=s.paid_at.isoformat() if s.paid_at else None,
            payment_reference=s.payment_reference,
        )
        for s in rows
    ]


class OwnerAdvanceOut(BaseModel):
    id: str
    advance_date: date
    amount: Decimal
    recovered_amount: Decimal
    outstanding: Decimal
    reason: str | None
    mode: str | None
    reference: str | None
    status: str


@router.get("/advances", response_model=list[OwnerAdvanceOut])
def my_advances(
    db: Session = Depends(get_db), owner_id: str = Depends(_my_owner), _=PortalDep
):
    """Cash already drawn, and what is left to come off a settlement.

    The commonest dispute between a contractor and an office is whether an
    advance was recovered twice. Both sides reading the same ledger is most
    of the answer.
    """
    rows = (
        db.execute(
            select(Advance)
            .where(Advance.vehicle_owner_id == owner_id)
            .order_by(Advance.advance_date.desc())
        )
        .scalars()
        .all()
    )
    return [
        OwnerAdvanceOut(
            id=str(a.id),
            advance_date=a.advance_date,
            amount=a.amount,
            recovered_amount=a.recovered_amount,
            outstanding=a.outstanding,
            reason=a.reason,
            mode=a.mode,
            reference=a.reference,
            status=str(a.status),
        )
        for a in rows
    ]
