"""Operational controls: the checks the office cannot run on paper.

Both checks in here exist because the paper process cannot do them, not because
they are clever. They are the reason a single database beats one spreadsheet
per vendor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.consignment import Box, Consignment
from app.models.enums import BoxStatus, FreightStatus
from app.models.fleet import Vehicle
from app.models.freight import Freight, FreightLeg, FreightPoint


@dataclass
class OdometerGap:
    """A vehicle's meter did not join up between two consecutive trips.

    A positive gap is usually a trip run for a different vendor division, which
    on paper sits on a different invoice and is therefore invisible. A negative
    gap cannot be legitimate and is always a data error.
    """

    vehicle_id: str
    registration_no: str
    previous_freight_id: str
    previous_trip_no: str
    previous_end_km: int
    next_freight_id: str
    next_trip_no: str
    next_start_km: int
    gap_km: int

    @property
    def is_negative(self) -> bool:
        return self.gap_km < 0

    @property
    def severity(self) -> str:
        if self.gap_km < 0:
            return "CRITICAL"
        if self.gap_km > 50:
            return "WARNING"
        return "INFO"


def detect_odometer_gaps(
    db: Session,
    *,
    since: date | None = None,
    tolerance_km: int = 0,
    limit: int = 50,
) -> list[OdometerGap]:
    """Walk each vehicle's legs in order and report where the chain breaks.

    Legs are ordered by when they started rather than by trip number, because
    trip numbers are issued when a trip is planned and vehicles do not
    necessarily run them in that order.
    """

    stmt = (
        select(FreightLeg)
        .join(Freight, FreightLeg.freight_id == Freight.id)
        .options(joinedload(FreightLeg.freight), joinedload(FreightLeg.vehicle))
        .where(
            FreightLeg.start_odometer.is_not(None),
            FreightLeg.end_odometer.is_not(None),
            Freight.status.notin_([FreightStatus.DRAFT, FreightStatus.CANCELLED]),
        )
    )
    if since is not None:
        stmt = stmt.where(Freight.trip_date >= since)

    legs = db.execute(stmt.order_by(FreightLeg.vehicle_id, FreightLeg.started_at)).scalars().all()

    gaps: list[OdometerGap] = []
    previous_by_vehicle: dict[str, FreightLeg] = {}

    for leg in legs:
        key = str(leg.vehicle_id)
        previous = previous_by_vehicle.get(key)
        if previous is not None:
            gap = (leg.start_odometer or 0) - (previous.end_odometer or 0)
            if gap < 0 or gap > tolerance_km:
                gaps.append(
                    OdometerGap(
                        vehicle_id=key,
                        registration_no=leg.vehicle.registration_no,
                        previous_freight_id=str(previous.freight_id),
                        previous_trip_no=previous.freight.trip_no,
                        previous_end_km=previous.end_odometer or 0,
                        next_freight_id=str(leg.freight_id),
                        next_trip_no=leg.freight.trip_no,
                        next_start_km=leg.start_odometer or 0,
                        gap_km=gap,
                    )
                )
        previous_by_vehicle[key] = leg

    # Negative gaps first - they are always errors - then the widest.
    gaps.sort(key=lambda g: (g.gap_km >= 0, -abs(g.gap_km)))
    return gaps[:limit]


@dataclass
class BoxReconciliation:
    """Loaded must equal delivered plus returned, or the trip does not close."""

    freight_id: str
    trip_no: str
    loaded: int
    delivered: int
    returned: int
    unaccounted: int

    @property
    def balances(self) -> bool:
        return self.unaccounted == 0


def reconcile_boxes(db: Session, freight_id) -> BoxReconciliation:
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise ValueError(f"No freight {freight_id}")

    point_ids = [p.id for p in freight.points]
    if not point_ids:
        return BoxReconciliation(str(freight.id), freight.trip_no, 0, 0, 0, 0)

    boxes = (
        db.execute(
            select(Box)
            .join(Consignment, Box.consignment_id == Consignment.id)
            .where(Consignment.freight_point_id.in_(point_ids))
        )
        .scalars()
        .all()
    )

    loaded = sum(
        1
        for b in boxes
        if b.status
        in {
            BoxStatus.LOADED,
            BoxStatus.IN_TRANSIT,
            BoxStatus.DELIVERED,
            BoxStatus.NOT_DELIVERED,
            BoxStatus.RETURNED_TO_WAREHOUSE,
            BoxStatus.DAMAGED,
        }
    )
    delivered = sum(1 for b in boxes if b.status == BoxStatus.DELIVERED)
    returned = sum(
        1
        for b in boxes
        if b.status in {BoxStatus.RETURNED_TO_WAREHOUSE, BoxStatus.DAMAGED}
    )

    return BoxReconciliation(
        freight_id=str(freight.id),
        trip_no=freight.trip_no,
        loaded=loaded,
        delivered=delivered,
        returned=returned,
        unaccounted=loaded - delivered - returned,
    )


def point_count_mismatches(db: Session, freight_id) -> list[dict]:
    """Points where the count out does not match the count in.

    This is the photo-checkpoint equivalent of a scan gap: it says a box is
    missing, and the two photographs say what was there at each end.
    """

    points = (
        db.execute(
            select(FreightPoint)
            .where(FreightPoint.freight_id == freight_id)
            .order_by(FreightPoint.sequence)
        )
        .scalars()
        .all()
    )

    return [
        {
            "point_id": str(p.id),
            "sequence": p.sequence,
            "loaded_box_count": p.loaded_box_count,
            "delivered_box_count": p.delivered_box_count,
            "difference": p.loaded_box_count - p.delivered_box_count,
        }
        for p in points
        if p.loaded_box_count != p.delivered_box_count
    ]


def next_lr_number(db: Session, vehicle_id) -> str:
    """Issue the next LR from this vehicle's book.

    LR numbers run per vehicle, which is why they do not appear in order down a
    vendor invoice. Confirmed as one LR per trip, issued by the application.
    """

    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise ValueError(f"No vehicle {vehicle_id}")

    number = vehicle.lr_next_number
    vehicle.lr_next_number = number + 1
    db.flush()
    return f"{vehicle.lr_prefix}{number}"
