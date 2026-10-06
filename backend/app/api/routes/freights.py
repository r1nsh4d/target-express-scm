"""Trips: build one, put a vehicle on it, send it out.

The lifecycle an admin drives:

    create (DRAFT)  ->  assign a vehicle and driver (PLANNED)
                    ->  confirm loading per point (LOADING)
                    ->  dispatch, which issues the LR (DISPATCHED)

From there the driver app takes over, and the trip completes when the vehicle
is back at the warehouse it left from.
"""

import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import BACK_OFFICE_ROLES, WAREHOUSE_ROLES, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.models.audit import AuditLog, OdometerCorrection
from app.models.consignee import Consignee
from app.models.enums import (
    FreightPointStatus,
    FreightStatus,
    GeoConfidence,
    LegChangeReason,
)
from app.models.fleet import Driver, Vehicle
from app.models.freight import Freight, FreightLeg, FreightPoint
from app.models.tracking import TrackingSession
from app.models.user import User
from app.models.vendor import VendorDivision, VendorWarehouse
from app.services.invoicing import billable_coolie, billable_unloading
from app.services.controls import next_lr_number
from app.services.rating import (
    RateCardNotFound,
    RateTerms,
    TripFacts,
    calculate_freight_charge,
    resolve_rate_card,
)

router = APIRouter(prefix="/api/freights", tags=["freights"])

ReadDep = Depends(require_roles(*BACK_OFFICE_ROLES))
OpsDep = Depends(require_roles(*WAREHOUSE_ROLES))

TRACKING_LINK_DAYS = 3


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #

class PointIn(BaseModel):
    consignee_id: str
    # Floor is a billable fact on furniture work, so it is captured up front and
    # confirmed by the driver at the door.
    floor_number: int = Field(default=0, ge=0, le=100)
    has_lift: bool = False
    planned_box_count: int = Field(default=0, ge=0)
    remarks: str | None = None


class FreightIn(BaseModel):
    vendor_division_id: str
    warehouse_id: str
    trip_date: date
    points: list[PointIn] = Field(min_length=1)
    remarks: str | None = None


class AssignIn(BaseModel):
    vehicle_id: str
    driver_id: str


class SwapVehicleIn(BaseModel):
    vehicle_id: str
    driver_id: str
    start_odometer: int = Field(ge=0)
    reason: LegChangeReason = LegChangeReason.BREAKDOWN
    notes: str | None = None


class LoadPointIn(BaseModel):
    loaded_box_count: int = Field(ge=0)
    loading_photo_url: str | None = None
    short_reason: str | None = None


class PointOut(BaseModel):
    id: str
    sequence: int
    consignee_id: str
    consignee_name: str
    address: str | None
    phone: str | None
    latitude: float | None = None
    longitude: float | None = None
    floor_number: int
    has_lift: bool
    loaded_box_count: int
    delivered_box_count: int
    unloading_paid: Decimal
    unloading_billed: Decimal
    coolie_paid: Decimal
    coolie_billed: Decimal
    coolie_note: str | None
    status: FreightPointStatus
    tracking_url: str | None = None


class LegOut(BaseModel):
    id: str
    sequence: int
    vehicle_id: str
    vehicle_no: str
    driver_id: str
    driver_name: str
    start_odometer: int | None
    end_odometer: int | None
    leg_distance_km: int | None
    change_reason: LegChangeReason


class FreightOut(BaseModel):
    id: str
    trip_no: str
    lr_no: str | None
    trip_date: date
    status: FreightStatus
    vendor_division_id: str
    vendor_division_name: str | None
    warehouse_id: str
    warehouse_name: str | None
    destination_text: str | None
    point_count: int
    billable_point_count: int
    delivered_point_count: int
    total_km: int | None
    has_returned: bool
    points: list[PointOut]
    legs: list[LegOut]


class FreightRowOut(BaseModel):
    id: str
    trip_no: str
    lr_no: str | None
    trip_date: date
    status: FreightStatus
    destination_text: str | None
    point_count: int
    vehicle_no: str | None
    driver_name: str | None
    total_km: int | None


class QuoteOut(BaseModel):
    """What this trip will bill, on the rate card in force on its date."""

    trip_no: str
    km: int
    points: int
    base_amount: Decimal
    extra_km: int
    extra_km_amount: Decimal
    extra_points: int
    extra_point_amount: Decimal
    unloading: Decimal
    toll: Decimal
    coolie: Decimal
    line_total: Decimal
    trace: list[str]


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _next_trip_no(db: Session, on: date) -> str:
    """Global sequence across every vendor, matching the Y26xxxxxx series."""
    prefix = f"Y{on.strftime('%y')}"
    count = db.scalar(
        select(func.count()).select_from(Freight).where(Freight.trip_no.like(f"{prefix}%"))
    )
    return f"{prefix}{(count or 0) + 1:06d}"


def _point_out(point: FreightPoint, include_tracking: bool = False) -> PointOut:
    consignee: Consignee = point.consignee
    out = PointOut(
        id=str(point.id),
        sequence=point.sequence,
        consignee_id=str(point.consignee_id),
        consignee_name=consignee.name,
        address=point.address_snapshot or consignee.address,
        phone=consignee.phone,
        latitude=float(point.latitude) if point.latitude is not None else None,
        longitude=float(point.longitude) if point.longitude is not None else None,
        floor_number=point.floor_number,
        has_lift=point.has_lift,
        loaded_box_count=point.loaded_box_count,
        delivered_box_count=point.delivered_box_count,
        unloading_paid=point.unloading_paid,
        unloading_billed=point.unloading_billed,
        coolie_paid=point.coolie_paid,
        coolie_billed=point.coolie_billed,
        coolie_note=point.coolie_note,
        status=point.status,
    )
    if include_tracking:
        session = next(
            (s for s in getattr(point, "_tracking_sessions", []) if s.is_active), None
        )
        if session is not None:
            out.tracking_url = f"{settings.public_base_url}/track/{session.token}"
    return out


def _freight_out(db: Session, freight: Freight) -> FreightOut:
    sessions = (
        db.execute(
            select(TrackingSession).where(
                TrackingSession.freight_point_id.in_([p.id for p in freight.points])
            )
        )
        .scalars()
        .all()
    )
    by_point: dict = {}
    for s in sessions:
        by_point.setdefault(s.freight_point_id, []).append(s)

    points = []
    for p in freight.points:
        p._tracking_sessions = by_point.get(p.id, [])
        points.append(_point_out(p, include_tracking=True))

    return FreightOut(
        id=str(freight.id),
        trip_no=freight.trip_no,
        lr_no=freight.lr_no,
        trip_date=freight.trip_date,
        status=freight.status,
        vendor_division_id=str(freight.vendor_division_id),
        vendor_division_name=freight.vendor_division.name if freight.vendor_division else None,
        warehouse_id=str(freight.warehouse_id),
        warehouse_name=freight.warehouse.name if freight.warehouse else None,
        destination_text=freight.destination_text,
        point_count=freight.point_count,
        billable_point_count=freight.billable_point_count,
        delivered_point_count=freight.delivered_point_count,
        total_km=freight.total_km,
        has_returned=freight.has_returned,
        points=points,
        legs=[
            LegOut(
                id=str(leg.id),
                sequence=leg.sequence,
                vehicle_id=str(leg.vehicle_id),
                vehicle_no=leg.vehicle.registration_no,
                driver_id=str(leg.driver_id),
                driver_name=leg.driver.name,
                start_odometer=leg.start_odometer,
                end_odometer=leg.end_odometer,
                leg_distance_km=leg.leg_distance_km,
                change_reason=leg.change_reason,
            )
            for leg in freight.legs
        ],
    )


def _load(db: Session, freight_id: str) -> Freight:
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return freight


# --------------------------------------------------------------------------- #
# Endpoints                                                                   #
# --------------------------------------------------------------------------- #

@router.get("", response_model=list[FreightRowOut])
def list_freights(
    status_filter: FreightStatus | None = Query(default=None, alias="status"),
    vendor_division_id: str | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _=ReadDep,
):
    stmt = (
        select(Freight)
        .options(joinedload(Freight.legs))
        .order_by(Freight.trip_date.desc(), Freight.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(Freight.status == status_filter)
    if vendor_division_id:
        stmt = stmt.where(Freight.vendor_division_id == vendor_division_id)

    rows = db.execute(stmt).unique().scalars().all()
    out = []
    for f in rows:
        leg = f.legs[0] if f.legs else None
        out.append(
            FreightRowOut(
                id=str(f.id),
                trip_no=f.trip_no,
                lr_no=f.lr_no,
                trip_date=f.trip_date,
                status=f.status,
                destination_text=f.destination_text,
                point_count=f.point_count,
                vehicle_no=leg.vehicle.registration_no if leg else None,
                driver_name=leg.driver.name if leg else None,
                total_km=f.total_km,
            )
        )
    return out


@router.post("", response_model=FreightOut, status_code=201)
def create_freight(payload: FreightIn, db: Session = Depends(get_db), user: User = OpsDep):
    division = db.get(VendorDivision, payload.vendor_division_id)
    if division is None:
        raise HTTPException(status_code=404, detail="Vendor division not found")
    warehouse = db.get(VendorWarehouse, payload.warehouse_id)
    if warehouse is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    freight = Freight(
        trip_no=_next_trip_no(db, payload.trip_date),
        trip_date=payload.trip_date,
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.DRAFT,
        point_count=len(payload.points),
        remarks=payload.remarks,
        created_by_id=user.id,
    )
    db.add(freight)
    db.flush()

    labels: list[str] = []
    for i, point in enumerate(payload.points, start=1):
        consignee = db.get(Consignee, point.consignee_id)
        if consignee is None:
            raise HTTPException(
                status_code=404, detail=f"Consignee not found for point {i}"
            )
        db.add(
            FreightPoint(
                freight_id=freight.id,
                sequence=i,
                consignee_id=consignee.id,
                # Snapshotted so a later edit to the customer record cannot
                # change what this trip was dispatched against.
                address_snapshot=consignee.address,
                latitude=consignee.latitude,
                longitude=consignee.longitude,
                floor_number=point.floor_number,
                has_lift=point.has_lift,
                loaded_box_count=point.planned_box_count,
                remarks=point.remarks,
            )
        )
        labels.append(consignee.city or consignee.name)

    # Same shape as the vendor invoice: a few place names, then the point count.
    seen: list[str] = []
    for label in labels:
        if label not in seen:
            seen.append(label)
    freight.destination_text = f"{', '.join(seen[:3])} ({len(payload.points)}PT)"

    db.commit()
    db.refresh(freight)
    return _freight_out(db, freight)


@router.get("/{freight_id}", response_model=FreightOut)
def get_freight(freight_id: str, db: Session = Depends(get_db), _=ReadDep):
    return _freight_out(db, _load(db, freight_id))


@router.post("/{freight_id}/assign", response_model=FreightOut)
def assign_vehicle(
    freight_id: str, payload: AssignIn, db: Session = Depends(get_db), _=OpsDep
):
    """Put a vehicle and driver on the trip. This opens leg 1."""
    freight = _load(db, freight_id)
    if freight.status not in (FreightStatus.DRAFT, FreightStatus.PLANNED):
        raise HTTPException(
            status_code=409, detail=f"A {freight.status} trip cannot be reassigned"
        )

    vehicle = db.get(Vehicle, payload.vehicle_id)
    driver = db.get(Driver, payload.driver_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if driver is None:
        raise HTTPException(status_code=404, detail="Driver not found")

    for leg in list(freight.legs):
        db.delete(leg)
    db.flush()

    db.add(
        FreightLeg(
            freight_id=freight.id,
            sequence=1,
            vehicle_id=vehicle.id,
            driver_id=driver.id,
            from_point_sequence=1,
            change_reason=LegChangeReason.INITIAL,
            # Pre-filled from the vehicle's last closing reading so the driver
            # confirms rather than types, which is where digits get dropped.
            start_odometer=None,
        )
    )
    freight.status = FreightStatus.PLANNED
    db.commit()
    db.refresh(freight)
    return _freight_out(db, freight)


@router.post("/{freight_id}/points/{point_id}/load", response_model=FreightOut)
def confirm_loading(
    freight_id: str,
    point_id: str,
    payload: LoadPointIn,
    db: Session = Depends(get_db),
    _=OpsDep,
):
    """Checkpoint one: count the boxes into the vehicle, photograph the stack."""
    freight = _load(db, freight_id)
    point = db.get(FreightPoint, point_id)
    if point is None or str(point.freight_id) != str(freight.id):
        raise HTTPException(status_code=404, detail="Point not found on this trip")

    point.loaded_box_count = payload.loaded_box_count
    point.loading_photo_url = payload.loading_photo_url
    point.loading_short_reason = payload.short_reason
    point.status = FreightPointStatus.LOADED

    if freight.status == FreightStatus.PLANNED:
        freight.status = FreightStatus.LOADING

    db.commit()
    db.refresh(freight)
    return _freight_out(db, freight)


class PointPatchIn(BaseModel):
    """A one-off correction for this stop only.

    The customer's own record is left alone: a warehouse round the back for one
    delivery should not become that customer's permanent address.
    """

    latitude: Decimal | None = None
    longitude: Decimal | None = None
    address_snapshot: str | None = None
    floor_number: int | None = Field(default=None, ge=0, le=100)
    has_lift: bool | None = None
    reference_image_url: str | None = None
    remarks: str | None = None

    # Unloading and coolie, recorded against the stop they happened at.
    #
    # Four numbers, not two, and every one of them is deliberate:
    #   unloading_paid    what went out to the labourers here
    #   unloading_billed  what the vendor is charged for it
    #   coolie_paid       cash a local porter gang demanded before unloading
    #   coolie_billed     what the vendor agreed to reimburse of that
    #
    # Paid and billed are separate because they genuinely differ - a spare-parts
    # run bills nothing for unloading while cash still leaves the driver's
    # pocket. Coolie is separate from unloading because a vendor asking "why has
    # unloading gone up" has to be able to see the two apart.
    unloading_paid: Decimal | None = Field(default=None, ge=0)
    unloading_billed: Decimal | None = Field(default=None, ge=0)
    coolie_paid: Decimal | None = Field(default=None, ge=0)
    coolie_billed: Decimal | None = Field(default=None, ge=0)
    # An unexplained cash line is the one a vendor refuses, so the note is what
    # makes it collectable.
    coolie_note: str | None = Field(default=None, max_length=2000)

    save_to_customer: bool = False


@router.patch("/{freight_id}/points/{point_id}", response_model=FreightOut)
def update_point(
    freight_id: str,
    point_id: str,
    payload: PointPatchIn,
    db: Session = Depends(get_db),
    _=OpsDep,
):
    freight = _load(db, freight_id)
    point = db.get(FreightPoint, point_id)
    if point is None or str(point.freight_id) != str(freight.id):
        raise HTTPException(status_code=404, detail="Point not found on this freight")

    data = payload.model_dump(exclude_unset=True, exclude={"save_to_customer"})
    for field, value in data.items():
        setattr(point, field, value)

    # Opt-in: keep the correction for next time as well as this trip.
    if payload.save_to_customer and point.consignee is not None:
        consignee = point.consignee
        if payload.latitude is not None:
            consignee.latitude = payload.latitude
        if payload.longitude is not None:
            consignee.longitude = payload.longitude
        if payload.latitude is not None or payload.longitude is not None:
            consignee.geo_confidence = GeoConfidence.VERIFIED
        if payload.address_snapshot:
            consignee.address = payload.address_snapshot

    db.commit()
    db.refresh(freight)
    return _freight_out(db, freight)


@router.post("/{freight_id}/dispatch", response_model=FreightOut)
def dispatch(freight_id: str, db: Session = Depends(get_db), _=OpsDep):
    """Send the vehicle out: issue the LR and open a tracking link per point."""
    freight = _load(db, freight_id)

    if freight.status not in (FreightStatus.PLANNED, FreightStatus.LOADING):
        raise HTTPException(
            status_code=409, detail=f"A {freight.status} trip cannot be dispatched"
        )
    if not freight.legs:
        raise HTTPException(
            status_code=409, detail="Assign a vehicle and driver before dispatching"
        )

    leg = freight.legs[0]
    if freight.lr_no is None:
        freight.lr_no = next_lr_number(db, leg.vehicle_id)

    expiry = datetime.now() + timedelta(days=TRACKING_LINK_DAYS)
    for point in freight.points:
        existing = db.execute(
            select(TrackingSession).where(
                TrackingSession.freight_point_id == point.id,
                TrackingSession.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                TrackingSession(
                    freight_point_id=point.id,
                    token=secrets.token_urlsafe(24),
                    expires_at=expiry,
                    sent_to_phone=point.consignee.phone,
                )
            )

    freight.status = FreightStatus.DISPATCHED
    freight.dispatched_at = datetime.now()
    db.commit()
    db.refresh(freight)
    return _freight_out(db, freight)


@router.post("/{freight_id}/swap-vehicle", response_model=FreightOut)
def swap_vehicle(
    freight_id: str, payload: SwapVehicleIn, db: Session = Depends(get_db), _=OpsDep
):
    """Breakdown mid-trip: close the current leg, open a second one.

    The vendor still sees one trip. Hire and driver pay split across the legs.
    """
    freight = _load(db, freight_id)
    if not freight.legs:
        raise HTTPException(status_code=409, detail="This trip has no vehicle on it yet")

    current = freight.legs[-1]
    if current.end_odometer is None:
        raise HTTPException(
            status_code=409,
            detail="Close the current leg's odometer reading before swapping the vehicle",
        )

    last_done = max(
        (p.sequence for p in freight.points if p.status != FreightPointStatus.PENDING),
        default=0,
    )
    current.to_point_sequence = last_done or None

    db.add(
        FreightLeg(
            freight_id=freight.id,
            sequence=current.sequence + 1,
            vehicle_id=payload.vehicle_id,
            driver_id=payload.driver_id,
            from_point_sequence=last_done + 1,
            start_odometer=payload.start_odometer,
            started_at=datetime.now(),
            change_reason=payload.reason,
            change_notes=payload.notes,
        )
    )
    db.commit()
    db.refresh(freight)
    return _freight_out(db, freight)


class OdometerCorrectionIn(BaseModel):
    field: str = Field(pattern="^(start_odometer|end_odometer)$")
    corrected_value: int = Field(ge=0, le=9_999_999)
    reason: str = Field(min_length=3, max_length=300)


@router.post("/{freight_id}/legs/{leg_id}/correct-odometer", response_model=FreightOut)
def correct_odometer(
    freight_id: str,
    leg_id: str,
    payload: OdometerCorrectionIn,
    db: Session = Depends(get_db),
    user: User = OpsDep,
):
    """Correct a meter reading, keeping what the driver actually entered.

    Billing is computed from these numbers, so a correction is its own record -
    original value, corrected value, reason and author. The driver's entry is
    never overwritten silently, because a vendor query six months later has to
    be able to show what was captured against what was billed.
    """
    freight = _load(db, freight_id)
    leg = db.get(FreightLeg, leg_id)
    if leg is None or str(leg.freight_id) != str(freight.id):
        raise HTTPException(status_code=404, detail="Leg not found on this freight")

    original = getattr(leg, payload.field)
    if original == payload.corrected_value:
        raise HTTPException(status_code=409, detail="That is already the recorded reading")

    db.add(
        OdometerCorrection(
            leg_id=leg.id,
            field=payload.field,
            original_value=original,
            corrected_value=payload.corrected_value,
            reason=payload.reason,
            corrected_by_id=user.id,
            corrected_at=datetime.now(),
        )
    )
    setattr(leg, payload.field, payload.corrected_value)

    if leg.start_odometer is not None and leg.end_odometer is not None:
        if leg.end_odometer < leg.start_odometer:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Closing reading {leg.end_odometer} would be below the opening "
                    f"reading {leg.start_odometer}"
                ),
            )
        leg.leg_distance_km = leg.end_odometer - leg.start_odometer

    freight.total_km = freight.round_trip_km
    if payload.field == "end_odometer":
        leg.vehicle.last_closing_km = payload.corrected_value

    db.commit()
    db.refresh(freight)
    return _freight_out(db, freight)


class OdometerCorrectionOut(BaseModel):
    leg_sequence: int
    field: str
    original_value: int | None
    corrected_value: int
    reason: str
    corrected_at: datetime


@router.get("/{freight_id}/corrections", response_model=list[OdometerCorrectionOut])
def list_corrections(freight_id: str, db: Session = Depends(get_db), _=ReadDep):
    """The audit trail for this freight's readings."""
    freight = _load(db, freight_id)
    by_leg = {leg.id: leg.sequence for leg in freight.legs}

    rows = (
        db.execute(
            select(OdometerCorrection)
            .where(OdometerCorrection.leg_id.in_(list(by_leg)))
            .order_by(OdometerCorrection.corrected_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        OdometerCorrectionOut(
            leg_sequence=by_leg.get(r.leg_id, 0),
            field=r.field,
            original_value=r.original_value,
            corrected_value=r.corrected_value,
            reason=r.reason,
            corrected_at=r.corrected_at,
        )
        for r in rows
    ]


@router.get("/{freight_id}/quote", response_model=QuoteOut)
def quote(freight_id: str, db: Session = Depends(get_db), _=ReadDep):
    """What this trip bills, on the card in force on its date.

    Available before completion so the office can sanity-check a trip rather
    than discovering the number at invoice time.
    """
    freight = _load(db, freight_id)

    vehicle_type_id = None
    if freight.legs and freight.legs[0].vehicle is not None:
        vehicle_type_id = freight.legs[0].vehicle.vehicle_type_id

    try:
        card = resolve_rate_card(
            db, freight.vendor_division_id, freight.trip_date, vehicle_type_id
        )
    except RateCardNotFound as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # The same arithmetic the invoice uses, not a second version of it.
    #
    # This previously summed `unloading_paid` - the cash that went OUT - while
    # the invoice bills `billable_unloading`, which is priced off the rate card
    # and the boxes. On furniture those are different numbers, so the screen
    # headed "What this bills" was quoting something the vendor is never
    # charged. A quote that disagrees with the invoice is worse than no quote.
    unloading = billable_unloading(db, freight, card)
    coolie = billable_coolie(freight)

    charge = calculate_freight_charge(
        RateTerms.from_rate_card(card),
        TripFacts(
            km=freight.total_km or freight.round_trip_km,
            points=freight.billable_point_count,
            unloading=unloading,
            coolie=coolie,
        ),
    )

    return QuoteOut(
        trip_no=freight.trip_no,
        km=freight.total_km or freight.round_trip_km,
        points=freight.billable_point_count,
        base_amount=charge.base_amount,
        extra_km=charge.extra_km,
        extra_km_amount=charge.extra_km_amount,
        extra_points=charge.extra_points,
        extra_point_amount=charge.extra_point_amount,
        unloading=charge.unloading,
        toll=charge.toll,
        coolie=charge.coolie,
        line_total=charge.line_total,
        trace=charge.trace,
    )


@router.delete("/{freight_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_freight(freight_id: str, db: Session = Depends(get_db), _=OpsDep):
    """Cancel rather than delete: a dispatched trip is a business record."""
    freight = _load(db, freight_id)
    if freight.status in (FreightStatus.BILLED, FreightStatus.SETTLED):
        raise HTTPException(status_code=409, detail="An invoiced trip cannot be cancelled")

    if freight.status == FreightStatus.DRAFT:
        db.delete(freight)
    else:
        freight.status = FreightStatus.CANCELLED
    db.commit()


# ---------------------------------------------------------------------------
# Editing a freight, and moving its status by hand
# ---------------------------------------------------------------------------


class FreightPatchIn(BaseModel):
    """Corrections to a freight that has not left yet.

    Everything is optional; only what is sent is changed. Points are sent whole
    when sent at all, because reordering is the common edit and a sequence of
    add/move/remove calls would leave the route half-applied if one failed.
    """

    trip_date: date | None = None
    warehouse_id: str | None = None
    remarks: str | None = None
    points: list[PointIn] | None = Field(default=None, min_length=1)


# Once a vehicle has been assigned and the LR issued, the points are what the
# driver is carrying and what the stickers were printed against. Changing them
# then means boxes on a lorry that match no stop.
EDITABLE_STATUSES = (FreightStatus.DRAFT, FreightStatus.PLANNED, FreightStatus.LOADING)


@router.patch("/{freight_id}", response_model=FreightOut)
def update_freight(
    freight_id: str,
    payload: FreightPatchIn,
    db: Session = Depends(get_db),
    _=OpsDep,
):
    """Correct a freight before it leaves.

    The vendor's requirement arrives on WhatsApp and changes twice before the
    lorry moves - a customer drops out, another is added, the date slips a day.
    Without this the only option was to cancel and rebuild, losing the trip
    number and anything already recorded against it.

    The vendor division is deliberately NOT editable. It decides which rate card
    prices the trip, and changing it after points and boxes exist would silently
    reprice work already done. Cancel and rebuild for that.
    """
    freight = _load(db, freight_id)

    if freight.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This freight is {freight.status.replace('_', ' ').lower()}. "
                "Only a trip that has not been dispatched can be edited."
            ),
        )

    if payload.trip_date is not None:
        freight.trip_date = payload.trip_date
    if payload.remarks is not None:
        freight.remarks = payload.remarks.strip() or None

    if payload.warehouse_id is not None:
        warehouse = db.get(VendorWarehouse, payload.warehouse_id)
        if warehouse is None:
            raise HTTPException(status_code=404, detail="Warehouse not found")
        freight.warehouse_id = warehouse.id

    if payload.points is not None:
        # A point that has already been loaded holds box counts and photographs.
        # Replacing the list wholesale would throw that away silently, so the
        # edit is refused and the user is told which stop is in the way.
        loaded = [p for p in freight.points if p.loaded_box_count or p.consignments]
        if loaded:
            names = ", ".join(sorted({p.consignee.name for p in loaded if p.consignee}))
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Boxes are already assigned at {names}. Clear those stops before "
                    "changing the route, or the loaded boxes would belong to no point."
                ),
            )

        for point in list(freight.points):
            db.delete(point)
        db.flush()

        labels: list[str] = []
        for i, point in enumerate(payload.points, start=1):
            consignee = db.get(Consignee, point.consignee_id)
            if consignee is None:
                raise HTTPException(status_code=404, detail=f"Consignee not found for point {i}")
            db.add(
                FreightPoint(
                    freight_id=freight.id,
                    sequence=i,
                    consignee_id=consignee.id,
                    address_snapshot=consignee.address,
                    latitude=consignee.latitude,
                    longitude=consignee.longitude,
                    floor_number=point.floor_number,
                    has_lift=point.has_lift,
                    loaded_box_count=point.planned_box_count,
                    remarks=point.remarks,
                )
            )
            labels.append(consignee.city or consignee.name)

        seen: list[str] = []
        for label in labels:
            if label not in seen:
                seen.append(label)
        freight.destination_text = f"{', '.join(seen[:3])} ({len(payload.points)}PT)"
        freight.point_count = len(payload.points)

    db.commit()
    db.refresh(freight)
    return _freight_out(db, freight)


class StatusOverrideIn(BaseModel):
    status: FreightStatus
    # Required, and that is the point. The normal route through these states is
    # dispatch, deliver, return - each of which records evidence. Jumping
    # straight to a status leaves no evidence at all, so the reason IS the
    # evidence, and it is written to the audit log.
    reason: str = Field(min_length=4, max_length=500)


# Statuses an admin may set by hand. BILLED and SETTLED are deliberately absent:
# those are set by issuing an invoice and by paying a settlement, and a freight
# marked BILLED with no invoice behind it is a hole in the accounts.
OVERRIDABLE = (
    FreightStatus.DRAFT,
    FreightStatus.PLANNED,
    FreightStatus.LOADING,
    FreightStatus.DISPATCHED,
    FreightStatus.IN_TRANSIT,
    FreightStatus.COMPLETED,
    FreightStatus.CANCELLED,
)


@router.post("/{freight_id}/status", response_model=FreightOut)
def override_status(
    freight_id: str,
    payload: StatusOverrideIn,
    db: Session = Depends(get_db),
    user: User = OpsDep,
):
    """Move a freight's status by hand, with a reason.

    Reality does not always reach the application. A driver's phone dies, a run
    is finished on paper, somebody forgets to press a button for two days. The
    alternative to this endpoint is an admin editing the database directly,
    which leaves no trace at all.

    So it exists, it is restricted, and every use is logged with who did it,
    what it was before, and why.
    """
    freight = _load(db, freight_id)

    if payload.status not in OVERRIDABLE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{payload.status} is not set by hand. It follows from issuing an "
                "invoice or recording a settlement."
            ),
        )

    if freight.status in (FreightStatus.BILLED, FreightStatus.SETTLED):
        raise HTTPException(
            status_code=409,
            detail=(
                "This freight has been invoiced. Changing its status now would make "
                "the invoice disagree with the trip it was built from."
            ),
        )

    if freight.status == payload.status:
        return _freight_out(db, freight)

    was = freight.status
    freight.status = payload.status

    db.add(
        AuditLog(
            actor_id=user.id,
            entity_type="freight",
            entity_id=freight.id,
            action="STATUS_OVERRIDE",
            actor_label=user.full_name,
            changes={"from": str(was), "to": str(payload.status)},
            # Written as a sentence as well as a diff: the person reading this
            # later is an admin answering a question, not a machine.
            note=(
                f"Status moved from {was} to {payload.status} by hand. "
                f"Reason: {payload.reason.strip()}"
            ),
        )
    )

    db.commit()
    db.refresh(freight)
    return _freight_out(db, freight)
