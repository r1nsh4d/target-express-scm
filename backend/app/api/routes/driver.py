from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.consignment import Box, Consignment
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
from app.models.expense import TripExpense
from app.models.fleet import Driver
from app.models.freight import Freight, FreightLeg, FreightPoint, PointUnloadingItem
from app.models.settlement import Advance, FreightPayout
from app.models.tracking import VehiclePing
from app.models.user import User
from app.services.completion import complete_freight_if_returned, record_leg_payouts
from app.services.controls import reconcile_boxes
from app.services.economics import driver_earnings_for_leg
from app.services.odometer import OdometerRefused, check_distance, check_opening
from app.services.rating import RateCardNotFound, money, resolve_rate_card
from app.services.unloading import (
    UnloadItem,
    calculate_point_driver_pay,
    calculate_point_unloading,
    division_pays_per_article,
    resolve_item_rates,
)

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


def _load_driver_freight(db: Session, freight_id: str, user: User) -> Freight:
    """The freight, if this driver is on it."""
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    driver = _driver_for(db, user)
    if not any(leg.driver_id == driver.id for leg in freight.legs):
        raise HTTPException(status_code=403, detail="This trip is not assigned to you")
    return freight


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

    # The continuity check the Vehicle model has always described and
    # nothing performed. A meter does not run backwards, and an opening
    # reading entered as 0 or 1 is what turned one Aluva run into a 180,015
    # km invoice line.
    try:
        check_opening(payload.reading, leg.vehicle.last_closing_km)
    except OdometerRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    leg.start_odometer = payload.reading
    leg.start_odometer_photo_url = payload.photo_url
    leg.started_at = datetime.now()

    freight = leg.freight
    if freight.status in (FreightStatus.PLANNED, FreightStatus.LOADING):
        freight.status = FreightStatus.DISPATCHED
        freight.dispatched_at = leg.started_at
    db.commit()


class PingIn(BaseModel):
    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)
    accuracy_m: int | None = None
    speed_kmph: Decimal | None = None
    # When the phone recorded it, which is not when it arrived. A lorry on the
    # Kasaragod road loses signal for twenty minutes at a time, and the points
    # it collected in that gap are the interesting ones.
    recorded_at: datetime | None = None


class PingBatchIn(BaseModel):
    # A batch, not a single point, because the phone buffers while it has no
    # signal and sends the backlog when it gets one. One request per point
    # would mean fifty requests the moment a bar appears, on a connection that
    # has just proved it is poor.
    pings: list[PingIn] = Field(min_length=1, max_length=500)


@router.post("/legs/{leg_id}/pings", status_code=status.HTTP_204_NO_CONTENT)
def record_pings(
    leg_id: str,
    payload: PingBatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> None:
    """Where the lorry is, from the driver's phone.

    This is what the customer's tracking page has always been able to draw and
    has never had anything to draw — the map could show a vehicle, and nothing
    in the application ever wrote one.

    Accepted only while the leg is actually running. A phone left on in a yard
    overnight would otherwise keep reporting a position long after the trip
    closed, and a customer opening an old link would watch a vehicle sitting
    somewhere it has no reason to be.

    Points outside Kerala and its neighbours are dropped rather than stored. A
    phone with a poor fix occasionally reports the middle of the ocean, and one
    such point drawn on a customer's map destroys the credibility of every
    other point on it.
    """
    leg = db.get(FreightLeg, leg_id)
    if leg is None:
        raise HTTPException(status_code=404, detail="Leg not found")

    driver = _driver_for(db, user)
    if leg.driver_id != driver.id:
        raise HTTPException(status_code=403, detail="This trip is not assigned to you")

    if leg.started_at is None or leg.ended_at is not None:
        # Not an error the driver can act on, and his phone will keep trying.
        # Accepting and discarding is kinder than a failure he cannot clear.
        return

    now = datetime.now()
    for ping in payload.pings:
        # Roughly peninsular India. Wide enough for any real trip out of
        # Kochi, narrow enough to catch a bad fix.
        if not (Decimal("6") <= ping.latitude <= Decimal("21")):
            continue
        if not (Decimal("68") <= ping.longitude <= Decimal("82")):
            continue

        recorded = ping.recorded_at or now
        # A clock set wrong on a cheap phone should not place a point in next
        # week, where it would sort above every genuine one.
        if recorded > now:
            recorded = now

        db.add(
            VehiclePing(
                freight_id=leg.freight_id,
                leg_id=leg.id,
                latitude=ping.latitude,
                longitude=ping.longitude,
                accuracy_m=ping.accuracy_m,
                speed_kmph=ping.speed_kmph,
                recorded_at=recorded,
            )
        )

    db.commit()


class ReturnScanIn(BaseModel):
    code: str = Field(min_length=1, max_length=120)
    # What happened to it. Refused at the door is the common one; damaged
    # matters more, because somebody has to be told before it is put back on
    # a shelf as good stock.
    status: BoxStatus = BoxStatus.RETURNED_TO_WAREHOUSE
    reason: str = Field(default="Came back on the vehicle", max_length=500)


class ReturnScanOut(BaseModel):
    result: str
    message: str
    barcode: str | None = None
    bill_no: str | None = None
    item_name: str | None = None
    # How the freight now reconciles, so the driver can see when he is done
    # rather than counting the pile himself.
    loaded: int
    delivered: int
    returned: int
    unaccounted: int


@router.post("/freights/{freight_id}/returns", response_model=ReturnScanOut)
def scan_returned_box(
    freight_id: str,
    payload: ReturnScanIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> ReturnScanOut:
    """A carton coming back off the vehicle at the warehouse.

    The last thing a trip needs before it closes: everything loaded was either
    delivered or came back, and until both halves are recorded the difference
    is "unaccounted" — which should mean a box nobody can find, not one
    standing in the godown.

    The driver does it rather than the office because he is the one unloading
    the vehicle, and a carton counted the next morning has already had a night
    to be misremembered.

    Never raises for a bad scan, for the same reason the delivery scanner does
    not: a man holding a carton in one hand needs a verdict on the screen, not
    an error dialog. Every outcome comes back 200 with a result the phone can
    colour.
    """
    freight = _load_driver_freight(db, freight_id, user)

    code = payload.code.strip().upper()
    box = (
        db.execute(
            select(Box)
            .join(Consignment, Box.consignment_id == Consignment.id)
            .join(FreightPoint, Consignment.freight_point_id == FreightPoint.id)
            .where(FreightPoint.freight_id == freight.id, func.upper(Box.barcode) == code)
        )
        .scalars()
        .first()
    )

    def reconciled(result: str, message: str, found: Box | None = None) -> ReturnScanOut:
        counts = reconcile_boxes(db, str(freight.id))
        return ReturnScanOut(
            result=result,
            message=message,
            barcode=found.barcode if found else None,
            bill_no=found.consignment.vendor_bill_no if found and found.consignment else None,
            item_name=found.item_name if found else None,
            loaded=counts.loaded,
            delivered=counts.delivered,
            returned=counts.returned,
            unaccounted=counts.unaccounted,
        )

    if box is None:
        # Either somebody else's carton or a misread sticker. Both are things
        # to say, not things to fail on.
        return reconciled("UNKNOWN", "That sticker is not on this trip.")

    if box.returned_at is not None:
        return reconciled("ALREADY", "Already recorded as returned.", box)

    if box.status == BoxStatus.DELIVERED:
        # Worth stopping on. A carton marked delivered that is physically on
        # the lorry means the delivery record is wrong, and quietly flipping
        # it would hide that.
        return reconciled(
            "WAS_DELIVERED",
            "This was marked delivered. Tell the office before putting it back.",
            box,
        )

    box.status = payload.status
    box.return_reason = payload.reason.strip() or "Came back on the vehicle"
    box.returned_at = datetime.now()
    box.returned_by_id = user.id
    db.commit()

    return reconciled("OK", "Recorded as returned.", box)


@router.get("/freights/{freight_id}/reconciliation", response_model=ReturnScanOut)
def freight_reconciliation(
    freight_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> ReturnScanOut:
    """Where the count stands, without scanning anything."""
    freight = _load_driver_freight(db, freight_id, user)
    counts = reconcile_boxes(db, str(freight.id))
    return ReturnScanOut(
        result="COUNT",
        message="",
        loaded=counts.loaded,
        delivered=counts.delivered,
        returned=counts.returned,
        unaccounted=counts.unaccounted,
    )


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
    try:
        check_distance(leg.start_odometer, payload.reading)
    except OdometerRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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
    return sorted(
        rows,
        key=lambda b: (b.consignment.vendor_bill_no if b.consignment else "", b.item_no),
    )


def _my_point(db: Session, point: FreightPoint, user: User) -> None:
    """Refuse a stop on somebody else's trip.

    The scan endpoint does not check this, and for a scan it hardly matters —
    the worst case is a driver seeing that a carton is not his. This writes
    money: what the vendor is charged for unloading and what a driver earns for
    it. So it checks.
    """
    driver = _driver_for(db, user)
    if not any(leg.driver_id == driver.id for leg in point.freight.legs):
        raise HTTPException(status_code=403, detail="This trip is not assigned to you")


class ArticleOut(BaseModel):
    item_code: str
    item_name: str
    # What one of these costs the vendor at THIS point's floor, and what the
    # driver earns for carrying it. Sent already priced so the phone can total
    # it without knowing anything about the rate card.
    vendor_each: Decimal
    driver_each: Decimal
    quantity: int


class UnloadingSheetOut(BaseModel):
    floor_number: int
    has_lift: bool
    articles: list[ArticleOut]
    vendor_total: Decimal
    driver_total: Decimal
    coolie_paid: Decimal
    coolie_note: str | None
    # False when no article rates are on file for this division, so there is
    # no list to fill in.
    priced_per_article: bool
    # Whether the vendor's rate card says unloading IS charged per article.
    #
    # These two were one flag, and the two states it ran together are not the
    # same thing at all. Spare parts are carried in and nothing is charged:
    # correct to show no list. Furniture where nobody has entered the article
    # rates yet looks identical from the rates table — and the screen simply
    # vanished, so the driver could log nothing, the vendor was charged
    # nothing, and no part of the system said why.
    charges_unloading: bool
    # Whether the driver's own side is shown. A driver on a rented vehicle is
    # paid by the vehicle's owner, not by Target Express, so a figure here
    # would be money he is never going to see. Decided on the server and the
    # numbers are zeroed before they are sent, rather than hidden by the
    # screen — a value that must not be shown should not be transmitted.
    shows_earnings: bool


def _unloading_sheet(
    db: Session, point: FreightPoint, user: User
) -> UnloadingSheetOut:
    freight = point.freight
    rates = resolve_item_rates(db, freight.vendor_division_id, freight.trip_date)
    shows_earnings = bool(user.can_view_earnings)

    logged = {
        row.item_code: row.quantity
        for row in db.execute(
            select(PointUnloadingItem).where(
                PointUnloadingItem.freight_point_id == point.id
            )
        ).scalars()
    }

    articles = [
        ArticleOut(
            item_code=rate.item_code,
            item_name=rate.item_name,
            vendor_each=rate.unit_charge(point.floor_number, point.has_lift),
            driver_each=(
                rate.unit_pay(point.floor_number, point.has_lift)
                if shows_earnings
                else Decimal("0.00")
            ),
            quantity=logged.get(rate.item_code, 0),
        )
        for rate in sorted(rates.values(), key=lambda r: r.item_name)
    ]

    return UnloadingSheetOut(
        floor_number=point.floor_number,
        has_lift=point.has_lift,
        articles=articles,
        vendor_total=money(
            sum((a.vendor_each * a.quantity for a in articles), Decimal("0"))
        ),
        driver_total=money(
            sum((a.driver_each * a.quantity for a in articles), Decimal("0"))
        ),
        shows_earnings=shows_earnings,
        coolie_paid=Decimal(point.coolie_paid or 0),
        coolie_note=point.coolie_note,
        priced_per_article=bool(rates),
        charges_unloading=_division_charges_unloading(db, freight),
    )


def _division_charges_unloading(db: Session, freight) -> bool:
    """Does this vendor's card say unloading is charged per article?

    Asked of the card rather than inferred from the rates table, because
    "nothing is charged here" and "nobody has entered the rates yet" are
    different problems and only one of them is somebody's job to fix.
    """
    vehicle_type_id = None
    if freight.legs and freight.legs[0].vehicle is not None:
        vehicle_type_id = freight.legs[0].vehicle.vehicle_type_id
    try:
        card = resolve_rate_card(
            db, freight.vendor_division_id, freight.trip_date, vehicle_type_id
        )
    except RateCardNotFound:
        # No card at all is a different failure, surfaced where the trip is
        # priced. It is not this screen's business to claim unloading is free.
        return False
    return str(card.unloading_basis) != "NOT_APPLICABLE"


@router.get("/points/{point_id}/unloading", response_model=UnloadingSheetOut)
def unloading_sheet(
    point_id: str,
    floor: int | None = Query(default=None, ge=0, le=100),
    lift: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> UnloadingSheetOut:
    """The articles this vendor pays unloading on, priced for this door.

    The floor and the lift can be overridden in the query so the phone reprices
    as the driver changes them, before anything is saved. He finds out the flat
    is on the third floor when he arrives, not when the trip was planned.
    """
    point = db.get(FreightPoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Point not found")
    _my_point(db, point, user)

    if floor is not None:
        point.floor_number = floor
    if lift is not None:
        point.has_lift = lift

    sheet = _unloading_sheet(db, point, user)
    # Nothing is saved by looking. The overrides above touched the in-memory
    # object only, so a driver who opens the screen and backs out has changed
    # nothing about what the vendor is charged.
    db.rollback()
    return sheet


class LoggedArticleIn(BaseModel):
    item_code: str = Field(min_length=1, max_length=48)
    quantity: int = Field(ge=0, le=999)


class UnloadingIn(BaseModel):
    articles: list[LoggedArticleIn] = []
    floor_number: int | None = Field(default=None, ge=0, le=100)
    has_lift: bool | None = None
    # Cash handed to a local porter gang. Not unloading, and never folded into
    # it — see the note on FreightPoint.coolie_paid.
    coolie_paid: Decimal | None = Field(default=None, ge=0)
    coolie_note: str | None = Field(default=None, max_length=300)


@router.post("/points/{point_id}/unloading", response_model=UnloadingSheetOut)
def log_unloading(
    point_id: str,
    payload: UnloadingIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> UnloadingSheetOut:
    """What the driver actually carried in, and up how many floors.

    This is the unloading charge sheet. It used to be worked out from the boxes
    on the bill, which is a guess at what happened: the bill says five chairs,
    four came off the lorry, one was refused at the door, and the sheet charged
    for five anyway. The man who carried them knows, and he has a phone in his
    hand.

    Both sides are priced here and stored on the point — what the vendor is
    charged and what the driver earns. One becomes the sheet pledged to the
    vendor, the other his pay, and they come off the same rate row for the same
    article on the same date so the margin is a subtraction.
    """
    point = db.get(FreightPoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Point not found")
    _my_point(db, point, user)

    if point.freight.status in (FreightStatus.BILLED, FreightStatus.SETTLED):
        raise HTTPException(
            status_code=409,
            detail=(
                "This trip has been invoiced. Changing the unloading now would make "
                "the invoice disagree with the trip it was built from."
            ),
        )

    # He is at the door, so he is the authority on the climb.
    if payload.floor_number is not None:
        point.floor_number = payload.floor_number
    if payload.has_lift is not None:
        point.has_lift = payload.has_lift

    freight = point.freight
    rates = resolve_item_rates(db, freight.vendor_division_id, freight.trip_date)

    # Replaced wholesale rather than merged, because the screen sends the whole
    # list every time and a quantity corrected from 4 to 3 has to go down.
    for existing in list(point.unloading_items):
        db.delete(existing)
    db.flush()

    unknown: list[str] = []
    # Kept as we go, rather than read back off the point afterwards.
    #
    # `point.unloading_items` was loaded by the delete loop above and does not
    # pick up rows added after it — so the list came back EMPTY and the charge
    # computed as zero. The quantities saved, which is why this looked like it
    # worked: the driver's counts came back when he reopened the screen, and
    # the money against them was nil. On screen it read "the unloading is not
    # saving", and it was the only part that was not.
    items: list[UnloadItem] = []
    for article in payload.articles:
        if article.quantity <= 0:
            continue
        rate = rates.get(article.item_code)
        if rate is None:
            unknown.append(article.item_code)
            continue
        db.add(
            PointUnloadingItem(
                freight_point_id=point.id,
                item_code=rate.item_code,
                item_name=rate.item_name,
                quantity=article.quantity,
            )
        )
        items.append(UnloadItem(item_code=rate.item_code, quantity=article.quantity))

    if unknown:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=f"No unloading rate for {', '.join(sorted(unknown))} on this vendor",
        )

    db.flush()
    charged = calculate_point_unloading(
        rates, items, floor_number=point.floor_number, has_lift=point.has_lift
    )
    point.unloading_billed = charged.total

    # What goes OUT at this door, as well as what the vendor is charged.
    #
    # This wrote only `unloading_billed`, so the cash the driver actually
    # hands the labourers stayed at zero on every point. Two things broke
    # quietly off that: the trip screen read "Unloading 140.00 (paid 0.00)"
    # on every furniture stop, and a driver on the older percentage-of-what-
    # was-paid arrangement earned a percentage of nothing.
    #
    # Only where the division prices the driver's side per article. Where it
    # does not, the percentage arrangement decides what leaves the pocket and
    # writing a figure here would be inventing one.
    if division_pays_per_article(rates):
        paid = calculate_point_driver_pay(
            rates, items, floor_number=point.floor_number, has_lift=point.has_lift
        )
        point.unloading_paid = paid.total

    if payload.coolie_paid is not None:
        point.coolie_paid = payload.coolie_paid
        # Reimbursed at what was actually handed over unless the office says
        # otherwise. A driver is not left out of pocket for somebody else's
        # demand at a market gate.
        point.coolie_billed = payload.coolie_paid
    if payload.coolie_note is not None:
        point.coolie_note = payload.coolie_note.strip() or None

    db.commit()
    db.refresh(point)
    return _unloading_sheet(db, point, user)


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
    point.remarks = payload.remarks

    # The article sheet wins where there is one.
    #
    # Two screens write this field. On furniture the driver counts the
    # articles and the rates decide what goes out, which is the figure the
    # vendor's charge is a subtraction from. The cash box on this form is for
    # everything else — a division with no article rates, where what he handed
    # over is the only record there is. Letting the form overwrite a priced
    # sheet means a driver who leaves the box blank zeroes his own unloading
    # pay after carrying forty chairs up three floors.
    logged_articles = bool([row for row in point.unloading_items if row.quantity > 0])
    if not logged_articles:
        point.unloading_paid = payload.unloading_paid
    point.departed_at = datetime.now()
    point.status = (
        FreightPointStatus.DELIVERED
        if payload.delivered_box_count >= point.loaded_box_count
        else FreightPointStatus.PART_DELIVERED
    )

    if payload.unloading_paid > 0 and not logged_articles:
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


class EarningLineOut(BaseModel):
    label: str
    amount: Decimal
    working: str


class TripEarningsOut(BaseModel):
    trip_no: str
    trip_date: date
    vehicle_no: str | None
    km: int
    points: int
    lines: list[EarningLineOut]
    total: Decimal
    # True once the trip is closed and the figures are what he WILL be paid
    # rather than what he is on course for.
    is_final: bool


@router.get("/freights/{freight_id}/earnings", response_model=TripEarningsOut)
def my_trip_earnings(
    freight_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.DRIVER)),
) -> TripEarningsOut:
    """What this run pays him, and how it was worked out.

    A month's total tells a driver nothing he can check. This is the one he
    can: his rate, the distance he actually drove, what the unloading came to
    article by article, and the sum of them. If it is wrong he can say which
    line is wrong, which is the difference between a query and a grievance.

    His side only. Nothing here says what the vendor was charged.
    """
    if not user.can_view_earnings:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Earnings are not shown on this login",
        )

    driver = _driver_for(db, user)
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    mine = [leg for leg in freight.legs if str(leg.driver_id) == str(driver.id)]
    if not mine:
        raise HTTPException(status_code=404, detail="You did not drive this trip")

    lines: list[EarningLineOut] = []
    total = Decimal("0")
    km = 0
    for leg in mine:
        leg_lines, leg_total = driver_earnings_for_leg(db, leg)
        km += leg.leg_distance_km or 0
        total += leg_total
        lines.extend(EarningLineOut(**line.__dict__) for line in leg_lines)

    vehicle_no = next(
        (leg.vehicle.registration_no for leg in mine if leg.vehicle is not None), None
    )

    return TripEarningsOut(
        trip_no=freight.trip_no,
        trip_date=freight.trip_date,
        vehicle_no=vehicle_no,
        km=km,
        points=freight.billable_point_count,
        lines=lines,
        total=money(total),
        is_final=freight.status
        in (FreightStatus.COMPLETED, FreightStatus.BILLED, FreightStatus.SETTLED),
    )


class FreightEarningOut(BaseModel):
    """One run, and what it paid him."""

    freight_id: str
    trip_no: str
    trip_date: date
    vehicle_no: str | None
    km: int
    amount: Decimal


class EarningsOut(BaseModel):
    period_from: date
    period_to: date
    # Run by run, newest first.
    #
    # The month's total and a split by head are both true and neither is
    # checkable: a driver cannot tell whether ₹2,975 is right, only whether it
    # feels low. What he CAN check is "the Kasaragod run on the 12th paid me
    # 420", because he remembers that run. Without this the figure is
    # something to be accepted or argued with, and there is no third option.
    freights: list[FreightEarningOut] = []
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
    per_freight: dict[str, Decimal] = {}
    for row in rows:
        by_head[str(row.head)] = by_head.get(str(row.head), Decimal("0")) + Decimal(row.amount)
        gross += Decimal(row.amount)
        key = str(row.freight_id)
        per_freight[key] = per_freight.get(key, Decimal("0")) + Decimal(row.amount)

    # The runs behind those totals, newest first. One query for the lot
    # rather than one per row — a month is thirty of them.
    freights: list[FreightEarningOut] = []
    if per_freight:
        for freight in (
            db.execute(
                select(Freight)
                .where(Freight.id.in_(list(per_freight)))
                .order_by(Freight.trip_date.desc(), Freight.trip_no.desc())
            )
            .scalars()
            .all()
        ):
            his = [leg for leg in freight.legs if str(leg.driver_id) == str(driver.id)]
            freights.append(
                FreightEarningOut(
                    freight_id=str(freight.id),
                    trip_no=freight.trip_no,
                    trip_date=freight.trip_date,
                    vehicle_no=next(
                        (
                            leg.vehicle.registration_no
                            for leg in his
                            if leg.vehicle is not None
                        ),
                        None,
                    ),
                    # His own legs' distance. On a trip he finished as a
                    # replacement, the kilometres the other man drove are not
                    # his and neither is the pay for them.
                    km=sum(leg.leg_distance_km or 0 for leg in his),
                    amount=money(per_freight[str(freight.id)]),
                )
            )

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
        freights=freights,
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
