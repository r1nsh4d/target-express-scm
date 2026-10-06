"""Closing a trip: the return to base, and the payouts that follow.

A trip is finished when the vehicle is back at the warehouse it left from - not
when the last point is delivered. That is what makes the billed kilometres a
closed round trip, and what lets the closing reading meet the next trip's
opening reading on the odometer chain.

Closing a leg writes its payouts. Doing it at close rather than at settlement
time means the terms in force on the day of the trip are the ones applied, even
if pay terms or hire terms change before the payment run.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import (
    FreightPointStatus,
    FreightStatus,
    HireRateBasis,
    PayeeType,
)
from app.models.fleet import Driver, DriverPayTerms, Vehicle, VehicleHireTerms
from app.models.freight import Freight, FreightLeg
from app.models.settlement import FreightPayout
from app.services.payout import (
    DriverPayRates,
    HireRates,
    LegFacts,
    compute_leg_payout,
    resolve_payee,
)
from app.services.settlement import recover_advances_for_freight


def _effective(stmt, model, on_date: date):
    return stmt.where(
        model.effective_from <= on_date,
        or_(model.effective_to.is_(None), model.effective_to >= on_date),
    ).order_by(model.effective_from.desc())


def resolve_driver_rates(db: Session, driver_id, on_date: date) -> DriverPayRates:
    terms = db.execute(
        _effective(
            select(DriverPayTerms).where(DriverPayTerms.driver_id == driver_id),
            DriverPayTerms,
            on_date,
        )
    ).scalars().first()

    if terms is None:
        # No terms on file is a data gap, not a zero-rate agreement. Recording
        # zero keeps the trip closeable and leaves the gap visible in reports
        # rather than silently inventing a rate.
        return DriverPayRates()

    return DriverPayRates(
        per_trip_amount=Decimal(terms.per_trip_amount),
        per_km_amount=Decimal(terms.per_km_amount),
        per_point_amount=Decimal(terms.per_point_amount),
        incentive_after_points=int(terms.incentive_after_points),
        daily_allowance=Decimal(terms.daily_allowance),
        unloading_share_percent=Decimal(terms.unloading_share_percent),
        unloading_share_basis=terms.unloading_share_basis,
    )


def resolve_hire_rates(db: Session, vehicle_id, on_date: date) -> HireRates:
    terms = db.execute(
        _effective(
            select(VehicleHireTerms).where(VehicleHireTerms.vehicle_id == vehicle_id),
            VehicleHireTerms,
            on_date,
        )
    ).scalars().first()

    if terms is None:
        return HireRates(rate_basis=HireRateBasis.PER_KM, rate_value=Decimal("0"))

    return HireRates(
        rate_basis=terms.rate_basis,
        rate_value=Decimal(terms.rate_value),
        minimum_km_per_trip=int(terms.minimum_km_per_trip),
        includes_unloading=bool(terms.includes_unloading),
        per_point_amount=Decimal(terms.per_point_amount),
        unloading_paid_to_owner=bool(terms.unloading_paid_to_owner),
    )


def leg_facts(db: Session, leg: FreightLeg) -> LegFacts:
    """What this leg did, for pay purposes.

    Points and unloading are counted only for the stops this leg actually
    covered, so a mid-trip vehicle change splits them correctly rather than
    paying both parties for the whole trip.
    """
    covered = [
        p
        for p in leg.freight.points
        if (leg.from_point_sequence is None or p.sequence >= leg.from_point_sequence)
        and (leg.to_point_sequence is None or p.sequence <= leg.to_point_sequence)
    ]
    # Attempted points, on the same rule as billing: a failed delivery still
    # counts because the vehicle went there. Only a point pulled from the route
    # before setting off is excluded.
    attempted = [p for p in covered if p.status != FreightPointStatus.SKIPPED]

    days = 1
    if leg.started_at and leg.ended_at:
        days = max(1, (leg.ended_at.date() - leg.started_at.date()).days + 1)

    return LegFacts(
        km=leg.leg_distance_km or 0,
        points=len(attempted),
        # Both unloading numbers reach the payout, because the driver's share
        # may be a percentage of either - see UnloadingShareBasis. Only the leg's
        # own points count: on a vehicle swap the second driver is not paid for
        # unloading the first one did.
        unloading_paid=sum((Decimal(p.unloading_paid or 0) for p in covered), Decimal("0")),
        unloading_billed=sum((Decimal(p.unloading_billed or 0) for p in covered), Decimal("0")),
        # Reimbursed in full to whoever handed it over, never shared.
        coolie_paid=sum((Decimal(p.coolie_paid or 0) for p in covered), Decimal("0")),
        days=days,
    )


def record_leg_payouts(db: Session, leg: FreightLeg) -> list[FreightPayout]:
    """Write one payout row per charge head for a closed leg.

    Idempotent: re-closing a leg replaces its payouts rather than doubling them.
    """
    existing = db.execute(
        select(FreightPayout).where(
            FreightPayout.leg_id == leg.id, FreightPayout.settlement_id.is_(None)
        )
    ).scalars().all()
    for row in existing:
        db.delete(row)

    vehicle: Vehicle = leg.vehicle
    driver: Driver = leg.driver
    on_date = leg.freight.trip_date
    payee_type = resolve_payee(vehicle.ownership)

    if payee_type == PayeeType.VEHICLE_OWNER:
        result = compute_leg_payout(
            vehicle.ownership,
            leg_facts(db, leg),
            hire_rates=resolve_hire_rates(db, vehicle.id, on_date),
        )
    else:
        result = compute_leg_payout(
            vehicle.ownership,
            leg_facts(db, leg),
            driver_rates=resolve_driver_rates(db, driver.id, on_date),
        )

    rows: list[FreightPayout] = []
    for line in result.lines:
        row = FreightPayout(
            freight_id=leg.freight_id,
            leg_id=leg.id,
            head=line.head,
            # Per line, not per leg: a rented trip pays the hire to the owner
            # and the unloading to the driver.
            payee_type=line.payee_type,
            # The driver is recorded even when the money goes to the owner: the
            # settlement document names him either way.
            driver_id=driver.id,
            vehicle_owner_id=(
                vehicle.owner_id if line.payee_type == PayeeType.VEHICLE_OWNER else None
            ),
            vehicle_id=vehicle.id,
            amount=line.amount,
            quantity=line.quantity,
            rate=line.rate,
            basis=line.basis,
        )
        db.add(row)
        rows.append(row)

    db.flush()
    return rows


def complete_freight_if_returned(db: Session, freight: Freight) -> bool:
    """Mark the trip complete once the vehicle is back at the origin warehouse.

    Returns True if this call completed it. A trip with an open leg is still
    running, whatever the delivery points say.
    """
    if freight.status in (FreightStatus.COMPLETED, FreightStatus.BILLED,
                          FreightStatus.SETTLED, FreightStatus.CANCELLED):
        return False

    if not freight.has_returned:
        return False

    now = datetime.now()
    freight.returned_at = max(
        (leg.ended_at for leg in freight.legs if leg.ended_at), default=now
    )
    freight.completed_at = now
    freight.total_km = freight.round_trip_km
    freight.status = FreightStatus.COMPLETED

    # Rented vehicles run a per-trip cycle: the owner drew an advance when the
    # vehicle left, and the trip's account closes by setting that advance
    # against what the trip earned. Doing it here means the balance payable is
    # ready the moment the vehicle is back.
    recover_advances_for_freight(db, freight)

    db.flush()
    return True
