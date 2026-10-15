"""The customer's tracking page.

Public and unauthenticated: the opaque token in the link is the credential. So
this module is deliberately narrow — it returns one delivery's own information
and nothing else. No vendor name, no other customers on the run, no driver
earnings, no freight total. A leaked link should reveal only what the person it
was sent to already knows.
"""

import math
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.clock import has_passed
from app.db.session import get_db
from app.models.consignment import Consignment
from app.models.enums import FreightPointStatus, FreightStatus, LocationChangeStatus
from app.models.freight import FreightPoint
from app.models.tracking import LocationChangeRequest, TrackingSession, VehiclePing

router = APIRouter(prefix="/api/track", tags=["tracking"])

# A correction further than this from the recorded pin changes billable
# distance, so an admin decides rather than the customer.
AUTO_APPROVE_METRES = 500


class TrackedBox(BaseModel):
    bill_no: str
    item_no: int
    of_total: int
    item_name: str | None
    delivered: bool


class VehiclePositionOut(BaseModel):
    latitude: float
    longitude: float
    recorded_at: datetime


class TrackingOut(BaseModel):
    """Only this delivery. Nothing about the rest of the run."""

    consignee_name: str
    address: str | None
    status: FreightPointStatus
    stop_number: int
    stops_before: int
    box_count: int
    boxes: list[TrackedBox]

    dispatched: bool
    planned_eta: datetime | None
    arrived_at: datetime | None
    delivered_at: datetime | None

    latitude: float | None
    longitude: float | None
    can_update_location: bool

    # --- what a consignment note needs ----------------------------------- #
    #
    # The LR is the document that travels with the goods, and the customer is
    # entitled to a copy of their part of it: which lorry, from where, under
    # which LR number, carrying which cartons. Everything here is about THEIR
    # delivery — the other stops on the run are none of their business and are
    # not sent.
    lr_no: str | None = None
    trip_no: str | None = None
    trip_date: date | None = None
    vendor_name: str | None = None
    from_warehouse: str | None = None
    from_address: str | None = None
    vehicle_no: str | None = None
    driver_name: str | None = None
    consignee_phone: str | None = None

    vehicle_position: VehiclePositionOut | None
    # How far the lorry still has to come, and roughly how long that takes.
    # Both are None until there is a position to measure from.
    distance_km: float | None = None
    eta_minutes: int | None = None
    driver_phone: str | None
    delivery_photo_url: str | None
    receiver_name: str | None
    # What they have already said, so the page shows it back rather than
    # asking twice.
    customer_rating: int | None = None
    customer_remarks: str | None = None


class LocationUpdateIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: str | None = None
    note: str | None = None


class LocationUpdateOut(BaseModel):
    status: LocationChangeStatus
    message: str


def _metres_between(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Haversine. Good enough to decide whether a correction needs approval."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(r * 2 * math.asin(math.sqrt(a)))


# Turning a straight line into a drive, and a drive into a time.
#
# Every number here is an assumption, and they are named rather than buried so
# that somebody who knows the roads better can change them.
#
# ROAD_FACTOR: roads are not straight lines. Kerala is long and thin with one
# coastal highway doing most of the work, so the drive is reliably longer than
# the crow flies — but not by much on a north-south run, which is most of them.
ROAD_FACTOR = 1.35
# A loaded lorry, averaged over highway, town and the inevitable halt. Not the
# speed it travels at; the speed it gets there at.
AVERAGE_KMPH = 34
# What a stop costs before the lorry moves again: finding the place, unloading,
# the receiver signing, the paperwork.
MINUTES_PER_STOP = 22
# Beyond this the estimate is not worth showing. A lorry 400 km away may be
# tomorrow, and "about 13 hours" reads as precision nobody has.
MAX_SENSIBLE_KM = 320


def _eta_minutes(distance_km: float, stops_ahead: int) -> int | None:
    """Roughly how long until the lorry is at the door.

    Deliberately coarse, and presented as such. A customer wants to know
    whether to wait in or go out, and an estimate honest about being an
    estimate serves that better than a precise-looking time that is wrong —
    which is what every delivery company's "arriving at 14:37" turns out to be.
    """
    if distance_km > MAX_SENSIBLE_KM:
        return None
    driving = (distance_km * ROAD_FACTOR / AVERAGE_KMPH) * 60
    return int(round(driving + stops_ahead * MINUTES_PER_STOP))


def _session(db: Session, token: str) -> TrackingSession:
    session = db.execute(
        select(TrackingSession).where(TrackingSession.token == token)
    ).scalar_one_or_none()

    # One message for every failure mode: a wrong token must not be
    # distinguishable from an expired one.
    if session is None or not session.is_active or has_passed(session.expires_at):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This tracking link is no longer active.",
        )
    return session


@router.get("/{token}", response_model=TrackingOut)
def track(token: str, db: Session = Depends(get_db)) -> TrackingOut:
    session = _session(db, token)

    point = db.get(FreightPoint, session.freight_point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="This tracking link is no longer active.")

    freight = point.freight
    dispatched = freight.status not in (FreightStatus.DRAFT, FreightStatus.PLANNED)

    session.view_count += 1
    session.last_viewed_at = datetime.now()

    boxes: list[TrackedBox] = []
    consignments = (
        db.execute(
            select(Consignment)
            .options(joinedload(Consignment.boxes))
            .where(Consignment.freight_point_id == point.id)
            .order_by(Consignment.vendor_bill_no)
        )
        .unique()
        .scalars()
        .all()
    )
    delivered = point.status in (
        FreightPointStatus.DELIVERED,
        FreightPointStatus.PART_DELIVERED,
    )
    for consignment in consignments:
        total = len(consignment.boxes)
        for box in sorted(consignment.boxes, key=lambda b: b.item_no):
            boxes.append(
                TrackedBox(
                    bill_no=consignment.vendor_bill_no,
                    item_no=box.item_no,
                    of_total=total,
                    item_name=box.item_name,
                    delivered=delivered,
                )
            )

    # How many stops are still ahead of this one — useful, and it gives nothing
    # away about who those customers are.
    stops_before = sum(
        1
        for p in freight.points
        if p.sequence < point.sequence
        and p.status
        not in (FreightPointStatus.DELIVERED, FreightPointStatus.PART_DELIVERED,
                FreightPointStatus.FAILED, FreightPointStatus.SKIPPED)
    )

    position = None
    driver_phone = None
    distance_km: float | None = None
    eta_minutes: int | None = None
    if dispatched and not delivered:
        ping = (
            db.execute(
                select(VehiclePing)
                .where(VehiclePing.freight_id == freight.id)
                .order_by(VehiclePing.recorded_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if ping is not None:
            position = VehiclePositionOut(
                latitude=float(ping.latitude),
                longitude=float(ping.longitude),
                recorded_at=ping.recorded_at,
            )
        leg = freight.legs[-1] if freight.legs else None
        driver_phone = leg.driver.phone if leg and leg.driver else None

        # Only measurable with both ends of the line. A customer whose pin has
        # never been dropped gets the map and no estimate, rather than an
        # estimate measured to the middle of their town.
        if ping is not None and point.latitude is not None and point.longitude is not None:
            metres = _metres_between(
                float(ping.latitude),
                float(ping.longitude),
                float(point.latitude),
                float(point.longitude),
            )
            distance_km = round(metres / 1000, 1)
            eta_minutes = _eta_minutes(distance_km, stops_before)

    db.commit()

    leg_any = freight.legs[-1] if freight.legs else None
    warehouse = freight.warehouse

    return TrackingOut(
        lr_no=freight.lr_no,
        trip_no=freight.trip_no,
        trip_date=freight.trip_date,
        vendor_name=(
            freight.vendor_division.vendor.name
            if freight.vendor_division and freight.vendor_division.vendor
            else None
        ),
        from_warehouse=warehouse.name if warehouse else None,
        from_address=warehouse.address if warehouse else None,
        vehicle_no=leg_any.vehicle.registration_no if leg_any and leg_any.vehicle else None,
        driver_name=leg_any.driver.name if leg_any and leg_any.driver else None,
        consignee_phone=point.consignee.phone,
        consignee_name=point.consignee.name,
        address=point.address_snapshot or point.consignee.address,
        status=point.status,
        stop_number=point.sequence,
        stops_before=stops_before,
        box_count=len(boxes) or point.loaded_box_count,
        boxes=boxes,
        dispatched=dispatched,
        planned_eta=point.planned_eta,
        arrived_at=point.arrived_at,
        delivered_at=point.departed_at if delivered else None,
        latitude=float(point.latitude) if point.latitude is not None else None,
        longitude=float(point.longitude) if point.longitude is not None else None,
        # Once it has been delivered there is nothing left to correct.
        can_update_location=not delivered,
        vehicle_position=position,
        distance_km=distance_km,
        eta_minutes=eta_minutes,
        driver_phone=driver_phone,
        customer_rating=point.customer_rating,
        customer_remarks=point.customer_remarks,
        delivery_photo_url=point.delivery_photo_url,
        receiver_name=point.receiver_name if delivered else None,
    )


class RatingIn(BaseModel):
    # One to five. Nullable on the way in too: somebody may want to leave a
    # remark without scoring anybody, and refusing that loses the remark.
    rating: int | None = Field(default=None, ge=1, le=5)
    remarks: str | None = Field(default=None, max_length=1000)


class RatingOut(BaseModel):
    rating: int | None
    remarks: str | None
    message: str


@router.post("/{token}/rating", response_model=RatingOut)
def rate_delivery(token: str, payload: RatingIn, db: Session = Depends(get_db)) -> RatingOut:
    """How the delivery went, in the consignee's own words.

    The only account of a delivery that does not come from the people who made
    it. A driver who is quick and careful and one who leaves cartons in the
    rain look identical in a box count, and the office has no other way to tell
    them apart.

    Only after the goods are in. Rating a delivery that has not happened is
    either a mistake or somebody rating the wait, and neither is what this
    measures.

    It can be changed while the link lives. Somebody who taps a star by
    accident on a phone should be able to put it right, and a rating nobody
    can correct is a rating nobody trusts.
    """
    session = _session(db, token)
    point = db.get(FreightPoint, session.freight_point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="This tracking link is no longer active.")

    if point.status not in (
        FreightPointStatus.DELIVERED,
        FreightPointStatus.PART_DELIVERED,
    ):
        raise HTTPException(
            status_code=409,
            detail="You can rate the delivery once the goods have been handed over.",
        )

    if payload.rating is None and not (payload.remarks or "").strip():
        raise HTTPException(status_code=422, detail="Leave a rating or a remark.")

    if payload.rating is not None:
        point.customer_rating = payload.rating
    if payload.remarks is not None:
        point.customer_remarks = payload.remarks.strip() or None
    point.rated_at = datetime.now()
    db.commit()
    db.refresh(point)

    return RatingOut(
        rating=point.customer_rating,
        remarks=point.customer_remarks,
        message="Thank you — this goes straight to the office.",
    )


@router.post("/{token}/location", response_model=LocationUpdateOut)
def update_location(
    token: str, payload: LocationUpdateIn, db: Session = Depends(get_db)
) -> LocationUpdateOut:
    """The customer corrects their own drop pin.

    A small correction is applied at once. A large one is queued for an admin,
    because moving the pin moves the billable distance.
    """
    session = _session(db, token)
    point = db.get(FreightPoint, session.freight_point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="This tracking link is no longer active.")

    if point.status in (FreightPointStatus.DELIVERED, FreightPointStatus.PART_DELIVERED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This delivery is already complete.",
        )

    old_lat = float(point.latitude) if point.latitude is not None else None
    old_lng = float(point.longitude) if point.longitude is not None else None

    distance = (
        _metres_between(old_lat, old_lng, payload.latitude, payload.longitude)
        if old_lat is not None and old_lng is not None
        else None
    )

    # No pin on file, or only a nudge: take it now.
    auto = distance is None or distance <= AUTO_APPROVE_METRES

    request = LocationChangeRequest(
        freight_point_id=point.id,
        consignee_id=point.consignee_id,
        old_latitude=Decimal(str(old_lat)) if old_lat is not None else None,
        old_longitude=Decimal(str(old_lng)) if old_lng is not None else None,
        new_latitude=Decimal(str(payload.latitude)),
        new_longitude=Decimal(str(payload.longitude)),
        distance_delta_m=distance,
        new_address=payload.address,
        requested_note=payload.note,
        status=LocationChangeStatus.AUTO_APPROVED if auto else LocationChangeStatus.PENDING,
    )
    db.add(request)

    if auto:
        point.latitude = request.new_latitude
        point.longitude = request.new_longitude
        if payload.address:
            point.address_snapshot = payload.address

        # Written back to the customer record too, so the next delivery to this
        # address is already right.
        consignee = point.consignee
        consignee.latitude = request.new_latitude
        consignee.longitude = request.new_longitude
        consignee.geo_confidence = "VERIFIED"
        if payload.address:
            consignee.address = payload.address

    db.commit()

    return LocationUpdateOut(
        status=request.status,
        message=(
            "Thank you — the driver will use the updated location."
            if auto
            else "Thank you. That is a fair distance from the address on file, so our office "
            "will confirm it before the driver sets off."
        ),
    )
