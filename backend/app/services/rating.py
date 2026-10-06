"""Freight rating.

The arithmetic is deliberately a pure function of plain values, with no ORM or
session in sight, so it can be tested directly against real invoices and reused
by the quote preview, the invoice run and the reports without drifting.

Verified against Target Express invoices 191/2026-27/022 and /023 (Godrej):

    line_total = base_trip_amount
               + max(0, km - included_km) * extra_km_rate
               + max(0, points - included_points) * extra_point_rate
               + toll + unloading + unloading_additional + detention

Every charge carries a human-readable trace line. A vendor query six months
later has to be answerable from the invoice alone, and "5100 = 300 km x 17" is
what makes that a thirty-second conversation instead of an argument.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rating import RateCard

TWO_PLACES = Decimal("0.01")


def money(value: Decimal | int | float | str) -> Decimal:
    """Round to paise, half-up, the way an invoice does."""
    return Decimal(str(value)).quantize(TWO_PLACES)


@dataclass(frozen=True)
class RateTerms:
    """The billable terms of a rate card, lifted out of the ORM object.

    Holding these separately is what lets a freight freeze its rates at
    dispatch: the snapshot is just this dataclass, serialised.
    """

    base_trip_amount: Decimal
    included_km: int
    extra_km_rate: Decimal
    included_points: int
    extra_point_rate: Decimal
    # Fixed amount covering the first `included_points` stops. Zero when the
    # allowance is already inside the trip base, as it is for Godrej.
    base_point_charge: Decimal = Decimal("0")

    @classmethod
    def from_rate_card(cls, card: RateCard) -> RateTerms:
        return cls(
            base_trip_amount=money(card.base_trip_amount),
            included_km=int(card.included_km),
            extra_km_rate=money(card.extra_km_rate),
            included_points=int(card.included_points),
            extra_point_rate=money(card.extra_point_rate),
            base_point_charge=money(card.base_point_charge),
        )

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> RateTerms:
        return cls(
            base_trip_amount=money(snapshot["base_trip_amount"]),
            included_km=int(snapshot["included_km"]),
            extra_km_rate=money(snapshot["extra_km_rate"]),
            included_points=int(snapshot["included_points"]),
            extra_point_rate=money(snapshot["extra_point_rate"]),
            base_point_charge=money(snapshot.get("base_point_charge", "0")),
        )

    def to_snapshot(self) -> dict:
        return {
            "base_trip_amount": str(self.base_trip_amount),
            "included_km": self.included_km,
            "extra_km_rate": str(self.extra_km_rate),
            "included_points": self.included_points,
            "extra_point_rate": str(self.extra_point_rate),
            "base_point_charge": str(self.base_point_charge),
        }


@dataclass(frozen=True)
class TripFacts:
    """What actually happened on the trip, as the invoice sees it."""

    km: int
    points: int
    toll: Decimal = Decimal("0")
    unloading: Decimal = Decimal("0")
    unloading_additional: Decimal = Decimal("0")
    detention: Decimal = Decimal("0")
    # Local porters who control unloading at some markets. Paid in cash at the
    # point and reimbursed by the vendor. Defaults to zero, so every freight
    # priced before this existed still prices to the same rupee.
    coolie: Decimal = Decimal("0")


@dataclass
class FreightCharge:
    """A fully worked invoice line, with its own explanation."""

    base_amount: Decimal
    included_km: int
    extra_km: int
    extra_km_rate: Decimal
    extra_km_amount: Decimal
    included_points: int
    extra_points: int
    extra_point_rate: Decimal
    extra_point_amount: Decimal
    toll: Decimal
    unloading: Decimal
    unloading_additional: Decimal
    detention: Decimal
    coolie: Decimal
    line_total: Decimal
    trace: list[str] = field(default_factory=list)

    def by_head(self) -> dict[str, Decimal]:
        """The billed side, grouped into the same heads the payout uses.

        Transportation is the base trip charge plus the distance beyond what the
        base includes: on the vendor's sheet those are two columns, but they are
        one head, and only the head is comparable against what is paid out.
        """
        from app.models.enums import ChargeHead

        return {
            ChargeHead.TRANSPORTATION: money(self.base_amount + self.extra_km_amount),
            ChargeHead.LOADING_UNLOADING: money(self.unloading + self.unloading_additional),
            ChargeHead.POINT_INCENTIVE: self.extra_point_amount,
            ChargeHead.TOLL: self.toll,
            ChargeHead.DETENTION: self.detention,
            # Deliberately NOT folded into LOADING_UNLOADING. Coolie money is a
            # local demand, not Target Express's unloading work, and a vendor
            # asking why unloading rose must be able to see the two apart.
            ChargeHead.COOLIE: self.coolie,
        }

    def as_dict(self) -> dict:
        return {
            "base_amount": str(self.base_amount),
            "included_km": self.included_km,
            "extra_km": self.extra_km,
            "extra_km_rate": str(self.extra_km_rate),
            "extra_km_amount": str(self.extra_km_amount),
            "included_points": self.included_points,
            "extra_points": self.extra_points,
            "extra_point_rate": str(self.extra_point_rate),
            "extra_point_amount": str(self.extra_point_amount),
            "toll": str(self.toll),
            "unloading": str(self.unloading),
            "unloading_additional": str(self.unloading_additional),
            "detention": str(self.detention),
            "coolie": str(self.coolie),
            "line_total": str(self.line_total),
            "trace": list(self.trace),
        }


def calculate_freight_charge(terms: RateTerms, facts: TripFacts) -> FreightCharge:
    """Price one trip. Pure: same inputs, same output, no I/O."""

    extra_km = max(0, facts.km - terms.included_km)
    extra_km_amount = money(Decimal(extra_km) * terms.extra_km_rate)

    # Points bill as a slab: a fixed amount covering the first `included_points`
    # stops, then a rate for each stop beyond.
    extra_points = max(0, facts.points - terms.included_points)
    extra_point_amount = money(
        terms.base_point_charge + Decimal(extra_points) * terms.extra_point_rate
    )

    toll = money(facts.toll)
    unloading = money(facts.unloading)
    unloading_additional = money(facts.unloading_additional)
    detention = money(facts.detention)
    coolie = money(facts.coolie)

    line_total = money(
        terms.base_trip_amount
        + extra_km_amount
        + extra_point_amount
        + toll
        + unloading
        + unloading_additional
        + detention
        + coolie
    )

    trace = [
        f"Base trip charge: {terms.base_trip_amount} "
        f"(includes {terms.included_km} km and {terms.included_points} points)",
        f"Extra distance: {facts.km} km - {terms.included_km} km included "
        f"= {extra_km} km x {terms.extra_km_rate} = {extra_km_amount}",
        (
            f"Points: {terms.base_point_charge} for the first {terms.included_points} "
            f"+ {extra_points} extra x {terms.extra_point_rate} = {extra_point_amount}"
            if terms.base_point_charge
            else f"Extra points: {facts.points} points - {terms.included_points} included "
            f"= {extra_points} x {terms.extra_point_rate} = {extra_point_amount}"
        ),
    ]
    if toll:
        trace.append(f"Toll (actual): {toll}")
    if unloading:
        trace.append(f"Unloading: {unloading}")
    if unloading_additional:
        trace.append(f"Unloading additional (actual): {unloading_additional}")
    if detention:
        trace.append(f"Detention (actual): {detention}")
    if coolie:
        trace.append(f"Coolie charges at points (actual): {coolie}")
    trace.append(f"Line total: {line_total}")

    return FreightCharge(
        base_amount=terms.base_trip_amount,
        included_km=terms.included_km,
        extra_km=extra_km,
        extra_km_rate=terms.extra_km_rate,
        extra_km_amount=extra_km_amount,
        included_points=terms.included_points,
        extra_points=extra_points,
        extra_point_rate=terms.extra_point_rate,
        extra_point_amount=extra_point_amount,
        toll=toll,
        unloading=unloading,
        unloading_additional=unloading_additional,
        detention=detention,
        coolie=coolie,
        line_total=line_total,
        trace=trace,
    )


class RateCardNotFound(Exception):
    """No card covers this division, vehicle type and date."""


def covers(card, on_date: date) -> bool:
    """Is this card in force on the given date?

    `effective_to` of None means open-ended. Both ends are inclusive: a card
    running to the 31st still prices a trip on the 31st.
    """
    if not getattr(card, "is_active", True):
        return False
    if card.effective_from > on_date:
        return False
    return card.effective_to is None or card.effective_to >= on_date


def select_effective_card(cards: Iterable, on_date: date, vehicle_type_id=None):
    """Choose which of a division's cards prices a trip on a date.

    Two rules, in order:

    1. A card naming the trip's vehicle type beats the catch-all card. So a
       vendor who later prices one vehicle type differently needs configuration,
       not code.
    2. Among equals, the latest `effective_from` wins - that is what makes a
       mid-contract rate change work: add a new card dated from the change, and
       trips before it keep pricing on the old one.

    Returns None when nothing covers that date, which is a real answer: it means
    the trip predates the contract, or falls in a gap between cards.
    """
    in_force = [c for c in cards if covers(c, on_date)]
    if not in_force:
        return None

    if vehicle_type_id is not None:
        specific = [c for c in in_force if c.vehicle_type_id == vehicle_type_id]
        if specific:
            return max(specific, key=lambda c: c.effective_from)

    generic = [c for c in in_force if c.vehicle_type_id is None]
    if generic:
        return max(generic, key=lambda c: c.effective_from)

    return None


def resolve_rate_card(
    db: Session,
    vendor_division_id,
    on_date: date,
    vehicle_type_id=None,
) -> RateCard:
    """Find the card in force for a division on a date.

    Rates are configured per vendor division and per date; this is what reads
    them back. One query for the division's cards, then the precedence rules
    above.
    """
    cards = (
        db.execute(select(RateCard).where(RateCard.vendor_division_id == vendor_division_id))
        .scalars()
        .all()
    )

    card = select_effective_card(cards, on_date, vehicle_type_id)
    if card is None:
        # Name the division, not its id. This message reaches an operator on the
        # trip screen, and "No rate card for division 78c9efe4-a71d-4751-..." is
        # not something anyone can act on. The lookup only runs on the failure
        # path, so it costs nothing in the normal case.
        from app.models.vendor import VendorDivision

        division = db.get(VendorDivision, vendor_division_id)
        name = division.name if division is not None else "this division"

        if cards:
            earliest = min(c.effective_from for c in cards)
            detail = (
                f"The earliest card for {name} starts on {earliest}. "
                "Add a card effective from a date on or before this trip."
            )
        else:
            detail = f"{name} has no rate cards at all yet. Add one under Rate cards."

        raise RateCardNotFound(f"No rate card covers {name} on {on_date}. {detail}")
    return card
