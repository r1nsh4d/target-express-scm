from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import BACK_OFFICE_ROLES, require_roles
from app.db.session import get_db
from app.models.billing import VendorInvoiceLine
from app.models.enquiry import Enquiry
from app.models.enums import EnquiryStatus, FreightPointStatus, FreightStatus
from app.models.freight import Freight, FreightLeg, FreightPoint
from app.services.controls import detect_odometer_gaps

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

ACTIVE_STATUSES = [FreightStatus.DISPATCHED, FreightStatus.IN_TRANSIT]


class OdometerGapOut(BaseModel):
    registration_no: str
    previous_trip_no: str
    previous_end_km: int
    next_trip_no: str
    next_start_km: int
    gap_km: int
    severity: str


class TripRowOut(BaseModel):
    id: str
    trip_no: str
    lr_no: str | None
    trip_date: date
    status: FreightStatus
    destination_text: str | None
    point_count: int
    points_delivered: int
    vehicle_no: str | None
    driver_name: str | None
    total_km: int | None


class DashboardSummary(BaseModel):
    as_of: date
    trips_today: int
    trips_active: int
    points_delivered_today: int
    points_pending_today: int
    boxes_loaded_today: int
    boxes_delivered_today: int
    uninvoiced_trip_count: int
    uninvoiced_since: date | None
    # Businesses who filled in the form on the website and have not been called.
    # The landing page promises them a call within one working day, and nothing
    # else in the product tells anyone they arrived.
    new_enquiry_count: int
    oldest_new_enquiry_at: datetime | None
    odometer_gaps: list[OdometerGapOut]
    recent_trips: list[TripRowOut]


@router.get("/summary", response_model=DashboardSummary)
def summary(
    db: Session = Depends(get_db),
    _=Depends(require_roles(*BACK_OFFICE_ROLES)),
) -> DashboardSummary:
    today = date.today()

    trips_today = db.scalar(
        select(func.count()).select_from(Freight).where(Freight.trip_date == today)
    )
    trips_active = db.scalar(
        select(func.count()).select_from(Freight).where(Freight.status.in_(ACTIVE_STATUSES))
    )

    delivered_today, pending_today = db.execute(
        select(
            func.count().filter(FreightPoint.status == FreightPointStatus.DELIVERED),
            func.count().filter(
                FreightPoint.status.in_(
                    [FreightPointStatus.PENDING, FreightPointStatus.LOADED,
                     FreightPointStatus.ARRIVED]
                )
            ),
        )
        .select_from(FreightPoint)
        .join(Freight, FreightPoint.freight_id == Freight.id)
        .where(Freight.trip_date == today)
    ).one()

    boxes_loaded, boxes_delivered = db.execute(
        select(
            func.coalesce(func.sum(FreightPoint.loaded_box_count), 0),
            func.coalesce(func.sum(FreightPoint.delivered_box_count), 0),
        )
        .select_from(FreightPoint)
        .join(Freight, FreightPoint.freight_id == Freight.id)
        .where(Freight.trip_date == today)
    ).one()

    # Completed trips that have not yet reached an invoice. This is the backlog
    # that turns a two-month billing lag into a number somebody owns.
    invoiced = select(VendorInvoiceLine.freight_id)
    uninvoiced_stmt = select(Freight).where(
        Freight.status == FreightStatus.COMPLETED,
        Freight.id.notin_(invoiced),
    )
    uninvoiced = db.execute(uninvoiced_stmt).scalars().all()
    uninvoiced_since = min((f.trip_date for f in uninvoiced), default=None)

    gaps = detect_odometer_gaps(db, since=today - timedelta(days=60), limit=8)

    # Website enquiries nobody has picked up yet. Spam is excluded - the office
    # should not be chased about a bot.
    new_enquiries = (
        db.execute(
            select(func.count(Enquiry.id)).where(
                Enquiry.status == EnquiryStatus.NEW,
                Enquiry.is_spam.is_(False),
            )
        ).scalar()
        or 0
    )
    oldest_enquiry = db.execute(
        select(func.min(Enquiry.created_at)).where(
            Enquiry.status == EnquiryStatus.NEW,
            Enquiry.is_spam.is_(False),
        )
    ).scalar()

    recent = (
        db.execute(
            select(Freight)
            .options(joinedload(Freight.points), joinedload(Freight.legs))
            .order_by(Freight.trip_date.desc(), Freight.created_at.desc())
            .limit(12)
        )
        .unique()
        .scalars()
        .all()
    )

    rows: list[TripRowOut] = []
    for freight in recent:
        first_leg: FreightLeg | None = freight.legs[0] if freight.legs else None
        rows.append(
            TripRowOut(
                id=str(freight.id),
                trip_no=freight.trip_no,
                lr_no=freight.lr_no,
                trip_date=freight.trip_date,
                status=freight.status,
                destination_text=freight.destination_text,
                point_count=freight.point_count or len(freight.points),
                points_delivered=sum(
                    1 for p in freight.points if p.status == FreightPointStatus.DELIVERED
                ),
                vehicle_no=first_leg.vehicle.registration_no if first_leg else None,
                driver_name=first_leg.driver.name if first_leg else None,
                total_km=freight.total_km,
            )
        )

    return DashboardSummary(
        as_of=today,
        trips_today=trips_today or 0,
        trips_active=trips_active or 0,
        points_delivered_today=delivered_today or 0,
        points_pending_today=pending_today or 0,
        boxes_loaded_today=int(boxes_loaded or 0),
        boxes_delivered_today=int(boxes_delivered or 0),
        uninvoiced_trip_count=len(uninvoiced),
        uninvoiced_since=uninvoiced_since,
        new_enquiry_count=new_enquiries,
        oldest_new_enquiry_at=oldest_enquiry,
        odometer_gaps=[
            OdometerGapOut(
                registration_no=g.registration_no,
                previous_trip_no=g.previous_trip_no,
                previous_end_km=g.previous_end_km,
                next_trip_no=g.next_trip_no,
                next_start_km=g.next_start_km,
                gap_km=g.gap_km,
                severity=g.severity,
            )
            for g in gaps
        ],
        recent_trips=rows,
    )
