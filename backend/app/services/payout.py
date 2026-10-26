"""The pay side of a trip.

A trip earns under three heads and pays out under the same three, so margin is
readable head by head rather than only as a single number at the bottom:

    TRANSPORTATION     base trip + distance
    LOADING_UNLOADING  loading and unloading
    POINT_INCENTIVE    points beyond those included

What the vendor is billed comes from the rate card (`services.rating`). What is
paid out comes from here, and the two are deliberately independent - on
spare-parts trips the vendor is billed nothing for unloading while money still
goes out, and that gap is the whole reason for splitting them.

Who gets paid is decided by the vehicle, not the trip:

    OWNED vehicle   -> the driver, on his pay terms
    RENTED vehicle  -> the vehicle's owner, on the hire terms

The driver is recorded on every payout row either way, because the settlement
document names the driver even when the money goes to the owner.

Pure functions, as with rating: no session, no ORM, so the arithmetic can be
tested directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.models.enums import (
    ChargeHead,
    HireRateBasis,
    PayeeType,
    UnloadingShareBasis,
    VehicleOwnership,
)
from app.services.rating import money


@dataclass(frozen=True)
class DriverPayRates:
    """Lifted from DriverPayTerms. Applies when the vehicle is owned.

    In practice Target Express pays its drivers on distance, plus the unloading
    cash where it applies, so `per_km_amount` and `unloading_share_percent` are
    the two that normally carry a value. The rest default to zero and are there
    for drivers on a different arrangement.

    Note that the point incentive the VENDOR is charged does not automatically
    reach the driver: `per_point_amount` is a separate, usually-zero setting.
    The difference is margin Target Express keeps.
    """

    per_km_amount: Decimal = Decimal("0")
    unloading_share_percent: Decimal = Decimal("0")
    # Which pot that percentage is OF. Defaults to what was paid out, because
    # the billed amount is ZERO on spare-parts runs while cash still leaves the
    # driver's pocket - see UnloadingShareBasis.
    unloading_share_basis: UnloadingShareBasis = UnloadingShareBasis.PAID_AT_POINT

    per_trip_amount: Decimal = Decimal("0")
    per_point_amount: Decimal = Decimal("0")
    # Stops before the incentive starts. 0 means every delivery point earns.
    incentive_after_points: int = 0
    daily_allowance: Decimal = Decimal("0")


@dataclass(frozen=True)
class HireRates:
    """Lifted from VehicleHireTerms. Applies when the vehicle is rented."""

    rate_basis: HireRateBasis = HireRateBasis.PER_KM
    rate_value: Decimal = Decimal("0")
    minimum_km_per_trip: int = 0
    includes_unloading: bool = False
    per_point_amount: Decimal = Decimal("0")
    # The hire settles to the owner, but the unloading money normally goes to
    # the driver, who is the one paying the labourers at the point.
    # A rented lorry is paid for AS A LORRY: one amount to its owner
    # covering the hire and the unloading both. Whether he drives it himself
    # or sends a man, and what he pays that man, is his business and not
    # Target Express's.
    #
    # This defaulted to False — the unloading going to the driver — which is
    # right for an OWNED lorry, where the driver is ours and the cash he
    # handed to the labourers is ours to reimburse. On a hired one it put
    # Target Express in the middle of an arrangement it is not part of, and
    # produced two settlements for one hire.
    unloading_paid_to_owner: bool = True


@dataclass(frozen=True)
class LegFacts:
    """What the leg actually did."""

    km: int = 0
    points: int = 0
    # Two unloading numbers, because the driver's share can be a percentage of
    # either and they are rarely the same figure.
    unloading_paid: Decimal = Decimal("0")
    unloading_billed: Decimal = Decimal("0")
    # Cash handed to local porters at the points. Reimbursed, never shared -
    # see the note in compute_driver_payout.
    coolie_paid: Decimal = Decimal("0")
    days: int = 1

    # What the driver earned by unloading, priced per article off the driver
    # column of the unloading rate card. When the division prices unloading per
    # article this REPLACES the percentage arrangement entirely: the vendor is
    # charged `a` for a chair and the driver is paid `b`, and the difference is
    # Target Express's margin.
    #
    # None means this division does not price unloading per article, and the
    # percentage applies instead. Zero is a different statement — a run where
    # nothing priced was carried — and must not be confused with it, or a
    # driver silently changes pay scheme on a quiet day.
    unloading_piece_pay: Decimal | None = None

    # What was agreed for THIS run, overriding the standing rate.
    #
    # Per-kilometre pay is right for the ordinary case and wrong for the ones
    # people ring about: a Kasaragod round trip settled as "twelve hundred for
    # the run" before the lorry leaves. An agreed figure replaces the
    # calculation outright rather than adding to it, because that is what the
    # word means — somebody looked at the job and said what it was worth.
    #
    # None means "work it out". Zero is a different statement: a run that pays
    # nothing for driving, which happens when a driver is being squared up
    # another way, and treating the two the same would silently stop paying
    # everybody.
    agreed_fare: Decimal | None = None
    agreed_unloading: Decimal | None = None


@dataclass
class PayoutLine:
    head: ChargeHead
    amount: Decimal
    payee_type: PayeeType = PayeeType.DRIVER
    quantity: Decimal | None = None
    rate: Decimal | None = None
    basis: str | None = None


@dataclass
class LegPayout:
    """What a leg pays out, which may be to more than one party.

    On a rented vehicle the hire settles to the owner while the unloading money
    goes to the driver, so a single leg can produce rows for both. `payee_type`
    names the primary payee - whoever the transportation belongs to.
    """

    payee_type: PayeeType
    lines: list[PayoutLine] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return money(sum((line.amount for line in self.lines), Decimal("0")))

    def by_head(self, head: ChargeHead, payee_type: PayeeType | None = None) -> Decimal:
        return money(
            sum(
                (
                    line.amount
                    for line in self.lines
                    if line.head == head
                    and (payee_type is None or line.payee_type == payee_type)
                ),
                Decimal("0"),
            )
        )

    def total_for(self, payee_type: PayeeType) -> Decimal:
        return money(
            sum(
                (line.amount for line in self.lines if line.payee_type == payee_type),
                Decimal("0"),
            )
        )

    @property
    def payees(self) -> list[PayeeType]:
        seen: list[PayeeType] = []
        for line in self.lines:
            if line.payee_type not in seen:
                seen.append(line.payee_type)
        return seen


def resolve_payee(ownership: VehicleOwnership) -> PayeeType:
    """Rent follows the vehicle; wages follow the driver."""
    return (
        PayeeType.VEHICLE_OWNER
        if ownership == VehicleOwnership.HIRED
        else PayeeType.DRIVER
    )


def compute_driver_payout(rates: DriverPayRates, facts: LegFacts) -> LegPayout:
    """Owned vehicle: the driver is paid."""
    lines: list[PayoutLine] = []

    if facts.agreed_fare is not None:
        transportation = money(facts.agreed_fare)
        fare_basis = f"agreed fare for this run - {facts.km} km, not charged by distance"
    else:
        transportation = money(
            rates.per_trip_amount
            + Decimal(facts.km) * rates.per_km_amount
            + Decimal(facts.days) * rates.daily_allowance
        )
        fare_basis = (
            f"trip {rates.per_trip_amount} + {facts.km} km x {rates.per_km_amount}"
            f" + {facts.days} day allowance x {rates.daily_allowance}"
        )

    if transportation:
        lines.append(
            PayoutLine(
                head=ChargeHead.TRANSPORTATION,
                amount=transportation,
                quantity=Decimal(facts.km),
                # No rate on an agreed fare, because there is not one. Putting
                # the per-km figure here would make a settlement document claim
                # arithmetic nobody did.
                rate=None if facts.agreed_fare is not None else rates.per_km_amount,
                basis=fare_basis,
            )
        )

    earning_points = max(0, facts.points - rates.incentive_after_points)
    incentive = money(Decimal(earning_points) * rates.per_point_amount)
    if incentive:
        lines.append(
            PayoutLine(
                head=ChargeHead.POINT_INCENTIVE,
                amount=incentive,
                quantity=Decimal(earning_points),
                rate=rates.per_point_amount,
                basis=(
                    f"{facts.points} points - {rates.incentive_after_points} before the "
                    f"incentive starts = {earning_points} x {rates.per_point_amount}"
                    if rates.incentive_after_points
                    else f"{facts.points} points x {rates.per_point_amount}"
                ),
            )
        )

    # The unloading charge is split: an agreed share to the driver, the
    # remainder kept by Target Express. Which pot the percentage applies to is
    # the driver's own arrangement - see UnloadingShareBasis. Getting this wrong
    # pays a real person the wrong money, so the basis is named in the line's
    # own explanation rather than left for someone to infer.
    out_of_pocket = money(facts.unloading_paid)

    if facts.agreed_unloading is not None:
        # An agreed figure for the run. Still floored at what he handed over,
        # because an agreement about what the work is worth is not an
        # agreement that he funds the labourers out of his own pocket.
        agreed = money(facts.agreed_unloading)
        unloading = max(agreed, out_of_pocket)
        if unloading:
            lines.append(
                PayoutLine(
                    head=ChargeHead.LOADING_UNLOADING,
                    amount=unloading,
                    quantity=facts.unloading_billed,
                    rate=None,
                    basis=(
                        f"{agreed} agreed for this run"
                        if unloading == agreed
                        else (
                            f"{agreed} agreed for this run, raised to {out_of_pocket} "
                            "actually paid out - a driver is never left out of pocket"
                        )
                    ),
                )
            )
    elif facts.unloading_piece_pay is not None:
        # Priced per article: the driver is paid for what he actually carried,
        # off his own column of the same rate row the vendor is charged from.
        # No percentage is involved, so there is nothing to floor — but he is
        # still never left out of pocket, because cash he handed to labourers
        # is his money until it comes back.
        piece = money(facts.unloading_piece_pay)
        unloading = max(piece, out_of_pocket)

        if unloading:
            if unloading > piece:
                basis = (
                    f"{piece} earned on the article rates, raised to "
                    f"{out_of_pocket} actually paid out at the points"
                    " - a driver is never left out of pocket"
                )
            else:
                retained = money(money(facts.unloading_billed) - unloading)
                basis = (
                    f"{piece} on the article rates"
                    f" - vendor billed {money(facts.unloading_billed)},"
                    f" Target Express keeps {retained}"
                )
            lines.append(
                PayoutLine(
                    head=ChargeHead.LOADING_UNLOADING,
                    amount=unloading,
                    quantity=facts.unloading_billed,
                    rate=Decimal("0"),
                    basis=basis,
                )
            )
    else:
        _percentage_unloading(lines, facts, rates, out_of_pocket)

    return _finish_driver_payout(lines, facts, rates)


def _percentage_unloading(lines, facts, rates, out_of_pocket: Decimal) -> None:
    """The older arrangement: a share of the unloading rather than a rate."""
    if rates.unloading_share_basis == UnloadingShareBasis.BILLED_TO_VENDOR:
        unloading_base = money(facts.unloading_billed)
        base_label = "billed to the vendor"
    else:
        unloading_base = out_of_pocket
        base_label = "paid out at the points"

    share = money(unloading_base * rates.unloading_share_percent / Decimal("100"))

    # The floor, and ONLY on the billed basis.
    #
    # On a spare-parts run the vendor is billed NOTHING for unloading while the
    # driver still pays the labourers, so a straight percentage of the billed
    # amount is zero and the driver would personally fund Target Express's
    # unloading. No arrangement means that, so the share is lifted to what he
    # actually handed over, and the line says plainly that it was.
    #
    # It must NOT apply on the paid basis. There, a share below 100% is the
    # whole arrangement - a driver on 60% of 500 is meant to receive 300, and
    # flooring that to 500 would make unloading_share_percent do nothing at all.
    if rates.unloading_share_basis == UnloadingShareBasis.BILLED_TO_VENDOR:
        unloading = max(share, out_of_pocket)
    else:
        unloading = share

    if unloading:
        if unloading > share:
            basis = (
                f"{rates.unloading_share_percent}% of {unloading_base} {base_label}"
                f" = {share}, raised to {out_of_pocket} actually paid out"
                " - a driver is never left out of pocket"
            )
        else:
            retained = money(unloading_base - unloading)
            basis = (
                f"{rates.unloading_share_percent}% of {unloading_base} {base_label}"
                f" - Target Express keeps {retained}"
            )

        lines.append(
            PayoutLine(
                head=ChargeHead.LOADING_UNLOADING,
                amount=unloading,
                quantity=unloading_base,
                rate=rates.unloading_share_percent,
                basis=basis,
            )
        )


def _finish_driver_payout(lines, facts, rates) -> LegPayout:
    """Whatever is paid the same way under either unloading arrangement."""
    # Coolie money is REIMBURSED IN FULL, never shared.
    #
    # It is not earnings. A local porter gang at a market demanded cash before
    # they would let the lorry be unloaded, and the driver paid it out of his
    # own pocket. Applying the unloading share to it would mean the driver
    # personally funding part of somebody else's extortion, which is not a pay
    # arrangement anyone agreed to.
    coolie = money(facts.coolie_paid)
    if coolie:
        lines.append(
            PayoutLine(
                head=ChargeHead.COOLIE,
                amount=coolie,
                quantity=coolie,
                rate=Decimal("100"),
                basis="coolie cash reimbursed at actuals - out of pocket, not earnings",
            )
        )

    return LegPayout(payee_type=PayeeType.DRIVER, lines=lines)


def compute_owner_payout(rates: HireRates, facts: LegFacts) -> LegPayout:
    """Rented vehicle: the vehicle's owner is paid."""
    lines: list[PayoutLine] = []

    if facts.agreed_fare is not None:
        # A lorry hired for one run at a figure settled on the phone. More
        # common on a market vehicle than a standing arrangement is, and until
        # now the only place to record it was a notebook.
        amount = money(facts.agreed_fare)
        basis = f"agreed hire for this run - {facts.km} km, not charged by distance"
        quantity: Decimal | None = Decimal(facts.km)
        agreed = True
    elif rates.rate_basis == HireRateBasis.PER_KM:
        agreed = False
        # A minimum guarantee means a short trip still bills at the floor.
        chargeable_km = max(facts.km, rates.minimum_km_per_trip)
        amount = money(Decimal(chargeable_km) * rates.rate_value)
        basis = f"{chargeable_km} km x {rates.rate_value}"
        if chargeable_km > facts.km:
            basis += f" (minimum {rates.minimum_km_per_trip} km applied, ran {facts.km})"
        quantity = Decimal(chargeable_km)
    elif rates.rate_basis == HireRateBasis.PER_DAY:
        agreed = False
        amount = money(Decimal(facts.days) * rates.rate_value)
        basis = f"{facts.days} day(s) x {rates.rate_value}"
        quantity = Decimal(facts.days)
    else:  # PER_TRIP
        agreed = False
        amount = money(rates.rate_value)
        basis = f"flat trip rate {rates.rate_value}"
        quantity = Decimal("1")

    if amount:
        lines.append(
            PayoutLine(
                head=ChargeHead.TRANSPORTATION,
                amount=amount,
                payee_type=PayeeType.VEHICLE_OWNER,
                quantity=quantity,
                # No rate on an agreed figure, because there is not one.
                rate=None if agreed else rates.rate_value,
                basis=basis,
            )
        )

    incentive = money(Decimal(facts.points) * rates.per_point_amount)
    if incentive:
        lines.append(
            PayoutLine(
                head=ChargeHead.POINT_INCENTIVE,
                amount=incentive,
                payee_type=PayeeType.VEHICLE_OWNER,
                quantity=Decimal(facts.points),
                rate=rates.per_point_amount,
                basis=f"{facts.points} points x {rates.per_point_amount}",
            )
        )

    # Unless the agreed rent already covers it, the unloading is reimbursed
    # to the OWNER, along with the hire. A hired lorry is paid for as a
    # lorry: one amount for the run and what was carried in, and the man at
    # the wheel is the owner's arrangement.
    #
    # The flag remains for the case where Target Express has agreed to pay a
    # hired driver directly, which happens and is worth being able to say.
    if not rates.includes_unloading:
        # An agreed figure for this run wins, floored at what was handed over
        # — nobody funds the labourers out of their own pocket.
        unloading = (
            max(money(facts.agreed_unloading), money(facts.unloading_paid))
            if facts.agreed_unloading is not None
            else money(facts.unloading_paid)
        )
        if unloading:
            to_owner = rates.unloading_paid_to_owner
            lines.append(
                PayoutLine(
                    head=ChargeHead.LOADING_UNLOADING,
                    amount=unloading,
                    payee_type=(
                        PayeeType.VEHICLE_OWNER if to_owner else PayeeType.DRIVER
                    ),
                    quantity=unloading,
                    rate=None,
                    basis=(
                        "unloading reimbursed at actuals to the vehicle owner"
                        if to_owner
                        else "unloading reimbursed at actuals to the driver, who "
                        "splits it with the cleaner and labourers"
                    ),
                )
            )

    return LegPayout(payee_type=PayeeType.VEHICLE_OWNER, lines=lines)


def compute_leg_payout(
    ownership: VehicleOwnership,
    facts: LegFacts,
    *,
    driver_rates: DriverPayRates | None = None,
    hire_rates: HireRates | None = None,
) -> LegPayout:
    """Single entry point: the vehicle decides which set of terms applies."""
    if resolve_payee(ownership) == PayeeType.VEHICLE_OWNER:
        if hire_rates is None:
            raise ValueError("A rented vehicle needs hire terms to compute its payout")
        return compute_owner_payout(hire_rates, facts)

    if driver_rates is None:
        raise ValueError("An owned vehicle needs driver pay terms to compute its payout")
    return compute_driver_payout(driver_rates, facts)


@dataclass
class TripMargin:
    """Billed against paid, head by head, for one trip."""

    billed: Decimal
    paid: Decimal

    @property
    def margin(self) -> Decimal:
        return money(self.billed - self.paid)

    @property
    def margin_percent(self) -> Decimal:
        if not self.billed:
            return Decimal("0.00")
        return money(self.margin / self.billed * Decimal("100"))
