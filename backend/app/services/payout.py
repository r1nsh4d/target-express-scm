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

from app.models.enums import ChargeHead, HireRateBasis, PayeeType, UnloadingShareBasis, VehicleOwnership
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
    unloading_paid_to_owner: bool = False


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

    transportation = money(
        rates.per_trip_amount
        + Decimal(facts.km) * rates.per_km_amount
        + Decimal(facts.days) * rates.daily_allowance
    )
    if transportation:
        lines.append(
            PayoutLine(
                head=ChargeHead.TRANSPORTATION,
                amount=transportation,
                quantity=Decimal(facts.km),
                rate=rates.per_km_amount,
                basis=(
                    f"trip {rates.per_trip_amount} + {facts.km} km x {rates.per_km_amount}"
                    f" + {facts.days} day allowance x {rates.daily_allowance}"
                ),
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

    if rates.rate_basis == HireRateBasis.PER_KM:
        # A minimum guarantee means a short trip still bills at the floor.
        chargeable_km = max(facts.km, rates.minimum_km_per_trip)
        amount = money(Decimal(chargeable_km) * rates.rate_value)
        basis = f"{chargeable_km} km x {rates.rate_value}"
        if chargeable_km > facts.km:
            basis += f" (minimum {rates.minimum_km_per_trip} km applied, ran {facts.km})"
        quantity: Decimal | None = Decimal(chargeable_km)
    elif rates.rate_basis == HireRateBasis.PER_DAY:
        amount = money(Decimal(facts.days) * rates.rate_value)
        basis = f"{facts.days} day(s) x {rates.rate_value}"
        quantity = Decimal(facts.days)
    else:  # PER_TRIP
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
                rate=rates.rate_value,
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

    # Unless the agreed rent already covers unloading, the cash paid out at the
    # points is reimbursed - to the DRIVER by default, because he is the one who
    # paid the labourers and splits it with the cleaner. The hire itself still
    # settles to the owner.
    if not rates.includes_unloading:
        unloading = money(facts.unloading_paid)
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
