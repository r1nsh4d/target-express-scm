from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.enums import (
    AdvanceStatus,
    BoxStatus,
    EntryMode,
    ExpenseType,
    FreightPointStatus,
    FreightStatus,
    PaidBy,
    PayeeType,
    UserRole,
)
from app.models.consignment import Box, Consignment
from app.models.expense import TripExpense
from app.models.fleet import Driver
from app.models.freight import Freight, FreightLeg, FreightPoint
from app.models.settlement import Advance, FreightPayout
from app.models.user import User
from app.services.completion import complete_freight_if_returned, record_leg_payouts

router = APIRouter(prefix="/api/driver", tags=["driver"])

OPEN_STATUSES = [
    FreightStatus.PLANNED,
    FreightStatus.LOADING,
    FreightStatus.DISPATCHED,
    FreightStatus.IN_TRANSIT,
]


class PointOut(BaseModel):
    id: str
    sequence: int
    consignee_name: str
    address: str | None
    phone: str | None
    latitude: float | None
    longitude: float | None
    floor_number: int = 0
    has_lift: bool = False
    loaded_box_count: int
    delivered_box_count: int
    status: FreightPointStatus
    unloading_paid: Decimal


class TripOut(BaseModel):
    id: str
    trip_no: str
    lr_no: str | None
    trip_date: date
    status: FreightStatus
    destination_text: str | None
    vehicle_no: str
    leg_id: str
    start_odometer: int | None
    end_odometer: int | None
    total_km: int | None = None
    origin_name: str | None = None
    origin_latitude: float | None = None
    origin_longitude: float | None = None
    points: list[PointOut]


class TripSummaryOut(BaseModel):
    id: str
    trip_no: str
    lr_no: str | None
    trip_date: date
    status: FreightStatus
    destination_text: str | None
    vehicle_no: str
    point_count: int
    delivered_point_count: int
    total_km: int | None
    is_open: bool


class OdometerIn(BaseModel):
    reading: int = Field(ge=0, le=9_999_999)
    photo_url: str | None = None


class DeliverIn(BaseModel):
    delivered_box_count: int = Field(ge=0)
    receiver_name: str | None = None
    delivery_photo_url: str | None = None
    unloading_paid: Decimal = Decimal("0")
    remarks: str | None = None


class ExpenseIn(BaseModel):
    type: ExpenseType
    amount: Decimal = Field(gt=0)
    receipt_photo_url: str | None = None
    paid_by: PaidBy = PaidBy.DRIVER
    freight_point_id: str | None = None
    remarks: str | None = None


def _driver_for(db: Session, user: User) -> Driver:
    driver = db.execute(select(Driver).where(Driver.user_id == user.id)).scalar_one_or_none()
    if driver is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No driver record is linked to this login",
        )
    return driver


def _open_leg(db: Session, driver: Driver) -> FreightLeg:
    leg = (
        db.execute(
            select(FreightLeg)
            .join(Freight, FreightLeg.freight_id == Freight.id)
            .options(joinedload(FreightLeg.freight), joinedload(FreightLeg.vehicle))
            .where(
                FreightLeg.driver_id == driver.id,
                FreightLeg.ended_at.is_(None),
                Freight.status.in_(OPEN_STATUSES),
            )
            .order_by(Freight.trip_date.desc())
        )
        .scalars()
        .first()
    )
    if leg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No open trip assigned to you"
        )
    return leg


def _points_of(db: Session, freight_id) -> list[PointOut]:
    points = (
        db.execute(
            select(FreightPoint)
            .options(joinedload(FreightPoint.consignee))
            .where(FreightPoint.freight_id == freight_id)
            .order_by(FreightPoint.sequence)
        )
        .scalars()
        .all()
    )
    return [
        PointOut(
            id=str(p.id),
            sequence=p.sequence,
            consignee_name=p.consignee.name,
            address=p.address_snapshot or p.consignee.address,
            phone=p.consignee.phone,
            latitude=float(p.latitude) if p.latitude is not None else None,
            longitude=float(p.longitude) if p.longitude is not None else None,
            floor_number=p.floor_number,
            has_lift=p.has_lift,
            loaded_box_count=p.loaded_box_count,
            delivered_box_count=p.delivered_box_count,
            status=p.status,
            unloading_paid=p.unloading_paid,
        )
        for p in points
    ]


def _trip_out(db: Session, leg: FreightLeg) -> TripOut:
    freight = leg.freight
    warehouse = freight.warehouse
    return TripOut(
        id=str(freight.id),
        trip_no=freight.trip_no,
        lr_no=freight.lr_no,
        trip_date=freight.trip_date,
        status=freight.status,
        destination_text=freight.destination_text,
        vehicle_no=leg.vehicle.registration_no,
        leg_id=str(leg.id),
        start_odometer=leg.start_odometer,
        end_odometer=leg.end_odometer,
        total_km=freight.total_km,
        # The run starts and ends here, so it is the origin of the route the
        # driver opens in Google Maps.
        origin_name=warehouse.name if warehouse else None,
        origin_latitude=float(warehouse.latitude)
        if warehouse and warehouse.latitude is not None
        else None,
        origin_longitude=float(warehouse.longitude)
        if warehouse and warehouse.longitude is not None
        else None,
        points=_points_of(db, freight.id),
    )


@router.get("/today", response_model=TripOut)
def today(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> TripOut:
    """The freight the driver is on right now."""
    return _trip_out(db, _open_leg(db, _driver_for(db, user)))


@router.get("/freights", response_model=list[TripSummaryOut])
def my_freights(
    scope: str = Query(default="all", pattern="^(open|past|all)$"),
    limit: int = Query(default=60, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> list[TripSummaryOut]:
    """Every freight assigned to this driver — what is running, and what he has
    already run."""
    driver = _driver_for(db, user)

    stmt = (
        select(FreightLeg)
        .join(Freight, FreightLeg.freight_id == Freight.id)
        .options(joinedload(FreightLeg.freight), joinedload(FreightLeg.vehicle))
        .where(FreightLeg.driver_id == driver.id)
    )
    if scope == "open":
        stmt = stmt.where(Freight.status.in_(OPEN_STATUSES))
    elif scope == "past":
        stmt = stmt.where(Freight.status.notin_(OPEN_STATUSES))

    legs = (
        db.execute(stmt.order_by(Freight.trip_date.desc(), Freight.created_at.desc()).limit(limit))
        .unique()
        .scalars()
        .all()
    )

    out: list[TripSummaryOut] = []
    for leg in legs:
        freight = leg.freight
        out.append(
            TripSummaryOut(
                id=str(freight.id),
                trip_no=freight.trip_no,
                lr_no=freight.lr_no,
                trip_date=freight.trip_date,
                status=freight.status,
                destination_text=freight.destination_text,
                vehicle_no=leg.vehicle.registration_no,
                point_count=freight.point_count,
                delivered_point_count=freight.delivered_point_count,
                total_km=freight.total_km,
                is_open=freight.status in OPEN_STATUSES,
            )
        )
    return out


@router.get("/freights/{freight_id}", response_model=TripOut)
def my_freight(
    freight_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> TripOut:
    """One of his own freights, in full. A driver can only open his own."""
    driver = _driver_for(db, user)
    leg = (
        db.execute(
            select(FreightLeg)
            .options(joinedload(FreightLeg.freight), joinedload(FreightLeg.vehicle))
            .where(FreightLeg.freight_id == freight_id, FreightLeg.driver_id == driver.id)
            .order_by(FreightLeg.sequence)
        )
        .scalars()
        .first()
    )
    if leg is None:
        raise HTTPException(status_code=404, detail="That freight is not assigned to you")
    return _trip_out(db, leg)


@router.post("/legs/{leg_id}/start", status_code=status.HTTP_204_NO_CONTENT)
def start_trip(
    leg_id: str,
    payload: OdometerIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> None:
    """Opening reading. Billing is computed from this pair, so the photograph
    of the meter is captured alongside it rather than as an afterthought."""
    leg = db.get(FreightLeg, leg_id)
    if leg is None:
        raise HTTPException(status_code=404, detail="Leg not found")

    driver = _driver_for(db, user)
    if leg.driver_id != driver.id:
        raise HTTPException(status_code=403, detail="This trip is not assigned to you")

    leg.start_odometer = payload.reading
    leg.start_odometer_photo_url = payload.photo_url
    leg.started_at = datetime.now()

    freight = leg.freight
    if freight.status in (FreightStatus.PLANNED, FreightStatus.LOADING):
        freight.status = FreightStatus.DISPATCHED
        freight.dispatched_at = leg.started_at
    db.commit()


@router.post("/legs/{leg_id}/close", status_code=status.HTTP_204_NO_CONTENT)
def close_trip(
    leg_id: str,
    payload: OdometerIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> None:
    leg = db.get(FreightLeg, leg_id)
    if leg is None:
        raise HTTPException(status_code=404, detail="Leg not found")

    driver = _driver_for(db, user)
    if leg.driver_id != driver.id:
        raise HTTPException(status_code=403, detail="This trip is not assigned to you")
    if leg.start_odometer is None:
        raise HTTPException(status_code=400, detail="Opening reading was never recorded")
    if payload.reading < leg.start_odometer:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Closing reading {payload.reading} is below the opening reading "
                f"{leg.start_odometer}"
            ),
        )

    leg.end_odometer = payload.reading
    leg.end_odometer_photo_url = payload.photo_url
    leg.ended_at = datetime.now()
    leg.leg_distance_km = payload.reading - leg.start_odometer

    # Keep the vehicle's last reading current so the next dispatch can check
    # continuity without walking history.
    leg.vehicle.last_closing_km = payload.reading

    freight = leg.freight
    freight.total_km = freight.round_trip_km

    # Pay is worked out now, on the terms in force on the day of the trip,
    # rather than at settlement time when those terms may have moved.
    record_leg_payouts(db, leg)

    # The trip is finished only once the vehicle is back at the warehouse it
    # left from - which is what a closed final leg means.
    complete_freight_if_returned(db, freight)

    db.commit()


class ScanIn(BaseModel):
    # Exactly what the camera read. Trimmed and upper-cased on the way in,
    # because a scanner sometimes appends whitespace and a person typing the
    # code off the sticker will not match our casing.
    code: str = Field(min_length=3, max_length=64)


class ScanOut(BaseModel):
    """What the driver's phone shows after each scan.

    Written for a screen glanced at while holding a carton: a verdict, a count,
    and if something is wrong, where the box actually belongs.
    """

    result: str  # OK | ALREADY | WRONG_POINT | UNKNOWN
    message: str
    barcode: str | None = None
    item_name: str | None = None
    bill_no: str | None = None
    # Where it should have gone, when it was scanned at the wrong stop. This is
    # the whole value of scanning: catching it at the door, not at the depot.
    belongs_to_point: int | None = None
    belongs_to_consignee: str | None = None

    scanned_count: int = 0
    expected_count: int = 0
    all_scanned: bool = False


@router.post("/points/{point_id}/scan", response_model=ScanOut)
def scan_box(
    point_id: str,
    payload: ScanIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> ScanOut:
    """Scan one carton off the vehicle at this stop.

    The reason this exists is not the count - the driver could type that. It is
    that a carton scanned here either belongs here or it does not, and the phone
    says so while the customer is still standing there. A wrong box found at the
    door is a thirty-second conversation; the same box found at the depot that
    night is a missing delivery, an angry vendor and a credit note.

    Never raises for a bad scan. A driver holding a carton in one hand needs a
    verdict on the screen, not an error dialog - so every outcome comes back 200
    with a `result` the phone can colour.
    """
    point = db.get(FreightPoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Point not found")

    code = payload.code.strip().upper()

    expected = _boxes_for_point(db, point)
    expected_ids = {b.id for b in expected}
    scanned_now = sum(1 for b in expected if b.scanned_at is not None)

    def result(kind: str, message: str, **extra) -> ScanOut:
        done = sum(1 for b in expected if b.scanned_at is not None)
        return ScanOut(
            result=kind,
            message=message,
            scanned_count=done,
            expected_count=len(expected),
            all_scanned=bool(expected) and done >= len(expected),
            **extra,
        )

    box = db.execute(
        select(Box).where(func.upper(Box.barcode) == code)
    ).scalar_one_or_none()

    if box is None:
        return result(
            "UNKNOWN",
            "That sticker is not from this application. Check it is a Target Express label.",
        )

    if box.id not in expected_ids:
        # The case worth building the whole feature for.
        other_point = box.consignment.freight_point if box.consignment else None
        return result(
            "WRONG_POINT",
            "This carton is NOT for this customer. Do not hand it over.",
            barcode=box.barcode,
            item_name=box.item_name,
            bill_no=box.consignment.vendor_bill_no if box.consignment else None,
            belongs_to_point=other_point.sequence if other_point else None,
            belongs_to_consignee=(
                other_point.consignee.name if other_point and other_point.consignee else None
            ),
        )

    if box.scanned_at is not None:
        # Scanning the same carton twice is a slip, not an error. Say so and
        # leave the count alone rather than double-counting it.
        return result(
            "ALREADY",
            f"Box {box.item_no} already scanned. Nothing counted twice.",
            barcode=box.barcode,
            item_name=box.item_name,
        )

    box.scanned_at = datetime.now()
    box.scanned_by_id = user.id
    box.status = BoxStatus.DELIVERED
    db.commit()

    scanned_now += 1
    done = scanned_now
    return ScanOut(
        result="OK",
        message=f"Box {box.item_no} confirmed.",
        barcode=box.barcode,
        item_name=box.item_name,
        bill_no=box.consignment.vendor_bill_no if box.consignment else None,
        scanned_count=done,
        expected_count=len(expected),
        all_scanned=bool(expected) and done >= len(expected),
    )


class PointBoxOut(BaseModel):
    id: str
    barcode: str
    item_no: int
    item_name: str | None
    bill_no: str
    scanned: bool


@router.get("/points/{point_id}/boxes", response_model=list[PointBoxOut])
def point_boxes(
    point_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.DRIVER)),
) -> list[PointBoxOut]:
    """Every carton that should come off at this stop, and which are confirmed.

    The list matters as much as the scanner: a driver whose camera will not
    focus in the dark still needs to see what he is carrying, and can tick them
    off by eye against the bill numbers.
    """
    point = db.get(FreightPoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Point not found")

    return [
        PointBoxOut(
            id=str(b.id),
            barcode=b.barcode,
            item_no=b.item_no,
            item_name=b.item_name,
            bill_no=b.consignment.vendor_bill_no if b.consignment else "—",
            scanned=b.scanned_at is not None,
        )
        for b in _boxes_for_point(db, point)
    ]


def _boxes_for_point(db: Session, point: FreightPoint) -> list[Box]:
    """Cartons belonging to this stop, in the order they are labelled."""
    rows = (
        db.execute(
            select(Box)
            .join(Consignment, Box.consignment_id == Consignment.id)
            .where(Consignment.freight_point_id == point.id)
            .options(joinedload(Box.consignment))
        )
        .unique()
        .scalars()
        .all()
    )
    return sorted(rows, key=lambda b: (b.consignment.vendor_bill_no if b.consignment else "", b.item_no))


@router.post("/points/{point_id}/deliver", status_code=status.HTTP_204_NO_CONTENT)
def deliver_point(
    point_id: str,
    payload: DeliverIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> None:
    """Checkpoint two: count out, photograph, receiver, unloading paid."""
    point = db.get(FreightPoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Point not found")

    point.delivered_box_count = payload.delivered_box_count
    point.receiver_name = payload.receiver_name
    point.delivery_photo_url = payload.delivery_photo_url
    point.unloading_paid = payload.unloading_paid
    point.remarks = payload.remarks
    point.departed_at = datetime.now()
    point.status = (
        FreightPointStatus.DELIVERED
        if payload.delivered_box_count >= point.loaded_box_count
        else FreightPointStatus.PART_DELIVERED
    )

    if payload.unloading_paid > 0:
        db.add(
            TripExpense(
                freight_id=point.freight_id,
                freight_point_id=point.id,
                type=ExpenseType.UNLOADING,
                amount=payload.unloading_paid,
                paid_by=PaidBy.DRIVER,
                entered_by_id=user.id,
                entry_mode=EntryMode.SELF,
            )
        )

    freight = point.freight
    if freight.status == FreightStatus.DISPATCHED:
        freight.status = FreightStatus.IN_TRANSIT
    db.commit()


class EarningsOut(BaseModel):
    period_from: date
    period_to: date
    trip_count: int
    by_head: dict[str, Decimal]
    gross: Decimal
    advance_outstanding: Decimal
    net: Decimal


@router.get("/earnings", response_model=EarningsOut)
def my_earnings(
    period_from: date | None = None,
    period_to: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> EarningsOut:
    """What this driver has earned, if his login is allowed to see it.

    Drivers on rented vehicles run trips but are not paid by Target Express, so
    the flag is off for them and this returns 403 rather than an empty screen -
    an empty total reads like a missing payment, which starts the wrong
    conversation.
    """
    if not user.can_view_earnings:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Earnings are not shown on this login",
        )

    driver = _driver_for(db, user)
    today = date.today()
    period_to = period_to or today
    period_from = period_from or period_to.replace(day=1)

    rows = (
        db.execute(
            select(FreightPayout)
            .join(Freight, FreightPayout.freight_id == Freight.id)
            .where(
                FreightPayout.driver_id == driver.id,
                FreightPayout.payee_type == PayeeType.DRIVER,
                Freight.trip_date >= period_from,
                Freight.trip_date <= period_to,
            )
        )
        .scalars()
        .all()
    )

    by_head: dict[str, Decimal] = {}
    gross = Decimal("0")
    for row in rows:
        by_head[str(row.head)] = by_head.get(str(row.head), Decimal("0")) + Decimal(row.amount)
        gross += Decimal(row.amount)

    advances = (
        db.execute(
            select(Advance).where(
                Advance.driver_id == driver.id,
                Advance.payee_type == PayeeType.DRIVER,
                Advance.status.in_([AdvanceStatus.OUTSTANDING, AdvanceStatus.PART_RECOVERED]),
            )
        )
        .scalars()
        .all()
    )
    outstanding = sum((a.outstanding for a in advances), Decimal("0"))

    return EarningsOut(
        period_from=period_from,
        period_to=period_to,
        trip_count=len({row.freight_id for row in rows}),
        by_head=by_head,
        gross=gross,
        advance_outstanding=outstanding,
        net=gross - outstanding,
    )


@router.post("/trips/{freight_id}/expenses", status_code=status.HTTP_201_CREATED)
def add_expense(
    freight_id: str,
    payload: ExpenseIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Drivers log their own. An admin with the same endpoint is recorded as
    ADMIN_ON_BEHALF, and the entry still shows in the driver's app."""
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    mode = EntryMode.SELF if user.role == UserRole.DRIVER else EntryMode.ADMIN_ON_BEHALF

    expense = TripExpense(
        freight_id=freight.id,
        freight_point_id=payload.freight_point_id,
        type=payload.type,
        amount=payload.amount,
        receipt_photo_url=payload.receipt_photo_url,
        paid_by=payload.paid_by,
        billable_to_vendor=payload.type in (ExpenseType.TOLL, ExpenseType.DETENTION),
        entered_by_id=user.id,
        entry_mode=mode,
        remarks=payload.remarks,
    )
    db.add(expense)
    db.commit()
    return {"id": str(expense.id), "entry_mode": mode}
