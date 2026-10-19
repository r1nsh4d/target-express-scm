"""What one freight earned, what it cost, and what is left.

Three people ask about the same trip and each needs a different cut of it.

THE DRIVER asks what he is getting. He wants his rate, the distance he
actually drove, what the unloading came to, and the total — in that order,
because that is the order he can check it in. He has no business seeing what
the vendor was charged.

THE OFFICE asks whether the trip was worth running. That needs both sides:
the base charge for this vehicle type, what it covers, the extra kilometres at
the extra rate, the points beyond those included, the unloading priced per
article and floor — and against it the driver's pay or the owner's hire, the
unloading that went out, and the road expenses. The difference is the margin.

Both come from here rather than from two screens that compute their own
version. The driver's total and the office's cost line are the same number,
and the only way to keep them that way is for there to be one of them.

EVERY LINE CARRIES ITS WORKING. `140 = 2 × 70` is checkable; `140` is
something you either believe or ring somebody about. The unloading lines go
further and name the article and the floor, because "why is unloading 340 on
this trip" is the question this whole module exists to answer without a phone
call.

A QUOTE, NOT A LEDGER. Before a trip is settled, the pay side is computed from
the terms in force — what it WOULD pay. Once payouts have been written it
reads them instead, because by then the question is what it DID pay, and the
two can legitimately differ after an office correction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    ApprovalStatus,
    ChargeHead,
    ExpenseType,
    PayeeType,
    VehicleOwnership,
)
from app.models.expense import TripExpense
from app.models.freight import Freight, FreightLeg
from app.models.settlement import FreightPayout
from app.services.completion import leg_facts, resolve_driver_rates, resolve_hire_rates
from app.services.invoicing import billable_coolie, billable_unloading
from app.services.payout import compute_leg_payout, resolve_payee
from app.services.rating import (
    RateCardNotFound,
    RateTerms,
    TripFacts,
    calculate_freight_charge,
    money,
    resolve_rate_card,
)
from app.services.unloading import (
    calculate_point_driver_pay,
    calculate_point_unloading,
    items_at_point,
    resolve_item_rates,
)

ZERO = Decimal("0.00")


@dataclass
class MoneyLine:
    """One figure, with the sum that produced it."""

    label: str
    amount: Decimal
    # The arithmetic in words: "40 km × ₹17.00". Empty where there is none to
    # show — a flat base charge is just a number.
    working: str = ""
    # For the driver's own view, where some lines are his and some are not.
    is_earning: bool = True


@dataclass
class UnloadingAtPoint:
    """One stop's unloading, both sides, article by article."""

    point_id: str
    sequence: int
    customer_name: str
    floor_number: int
    has_lift: bool
    articles: list[dict] = field(default_factory=list)
    charged: Decimal = ZERO
    driver_pay: Decimal = ZERO

    @property
    def margin(self) -> Decimal:
        return money(self.charged - self.driver_pay)


@dataclass
class FreightEconomics:
    trip_no: str
    trip_date: str
    status: str
    vehicle_no: str | None
    vehicle_type_name: str | None
    driver_name: str | None
    km: int
    points: int

    # What the vendor pays.
    revenue: list[MoneyLine] = field(default_factory=list)
    revenue_total: Decimal = ZERO
    # Why there is no revenue, when there is none.
    revenue_problem: str | None = None

    # What goes out, and to whom.
    cost: list[MoneyLine] = field(default_factory=list)
    cost_total: Decimal = ZERO
    paid_to: str = "DRIVER"
    # True once real payout rows exist, so the screen can say whether these
    # are figures or forecasts.
    is_settled: bool = False

    unloading_points: list[UnloadingAtPoint] = field(default_factory=list)

    @property
    def margin(self) -> Decimal:
        return money(self.revenue_total - self.cost_total)

    @property
    def margin_percent(self) -> Decimal:
        if not self.revenue_total:
            return ZERO
        return money(self.margin / self.revenue_total * Decimal("100"))

    @property
    def margin_per_km(self) -> Decimal:
        if not self.km:
            return ZERO
        return money(self.margin / Decimal(self.km))


def _rupees(value: Decimal) -> str:
    return f"₹{Decimal(value):,.2f}"


def unloading_detail(db: Session, freight: Freight) -> list[UnloadingAtPoint]:
    """Every stop's unloading, priced both ways off the same count.

    The articles are what the driver counted through the door where he
    recorded them. The vendor's price and the driver's pay come off the same
    rate row for the same article on the same date, so the margin on a chair
    is a subtraction rather than a reconciliation.
    """
    rates = resolve_item_rates(db, freight.vendor_division_id, freight.trip_date)
    if not rates:
        return []

    out: list[UnloadingAtPoint] = []
    for point in freight.points:
        items = items_at_point(point)
        if not items:
            continue

        charged = calculate_point_unloading(
            rates, items, floor_number=point.floor_number, has_lift=point.has_lift
        )
        pay = calculate_point_driver_pay(
            rates, items, floor_number=point.floor_number, has_lift=point.has_lift
        )
        pay_by_code = {line.item_code: line for line in pay.lines}

        out.append(
            UnloadingAtPoint(
                point_id=str(point.id),
                sequence=point.sequence,
                customer_name=point.consignee.name if point.consignee else "—",
                floor_number=point.floor_number,
                has_lift=point.has_lift,
                articles=[
                    {
                        "item_name": line.item_name,
                        "quantity": line.quantity,
                        "charged_each": line.unit_charge,
                        "charged": line.amount,
                        # `unit_charge` on a driver-pay line is the driver's
                        # unit rate: the same dataclass, run down the driver
                        # column of the same rate row.
                        "driver_each": (
                            pay_by_code[line.item_code].unit_charge
                            if line.item_code in pay_by_code
                            else ZERO
                        ),
                        "driver_pay": (
                            pay_by_code[line.item_code].amount
                            if line.item_code in pay_by_code
                            else ZERO
                        ),
                        "floors_charged": line.floors_charged,
                    }
                    for line in charged.lines
                ],
                charged=charged.total,
                driver_pay=pay.total,
            )
        )
    return out


def _revenue(db: Session, freight: Freight) -> tuple[list[MoneyLine], Decimal, str | None]:
    """What the vendor pays, head by head, with the card's own figures named."""
    vehicle_type_id = None
    if freight.legs and freight.legs[0].vehicle is not None:
        vehicle_type_id = freight.legs[0].vehicle.vehicle_type_id

    try:
        card = resolve_rate_card(
            db, freight.vendor_division_id, freight.trip_date, vehicle_type_id
        )
    except RateCardNotFound as exc:
        return [], ZERO, str(exc)

    charge = calculate_freight_charge(
        RateTerms.from_rate_card(card),
        TripFacts(
            km=freight.total_km or freight.round_trip_km,
            points=freight.billable_point_count,
            unloading=billable_unloading(db, freight, card),
            coolie=billable_coolie(freight),
        ),
    )

    lines = [
        MoneyLine(
            label="Base charge for the trip",
            amount=charge.base_amount,
            working=(
                f"covers {card.included_km} km and {card.included_points} "
                f"{'point' if card.included_points == 1 else 'points'}"
            ),
        )
    ]

    # Shown even at zero, both of them. "Extra distance ₹0.00" with its
    # working beside it is the sentence that explains why a 40 km run bills
    # the same as a 58 km one, and leaving it out is how that becomes a
    # question for the office.
    lines.append(
        MoneyLine(
            label="Extra distance",
            amount=charge.extra_km_amount,
            working=(
                f"{charge.extra_km} km over {card.included_km} × {_rupees(card.extra_km_rate)}"
                if charge.extra_km
                else (
                    f"{freight.total_km or freight.round_trip_km} km, "
                    f"within the {card.included_km} included"
                )
            ),
        )
    )
    lines.append(
        MoneyLine(
            label="Extra points",
            amount=charge.extra_point_amount,
            working=(
                f"{charge.extra_points} over {card.included_points} × "
                f"{_rupees(card.extra_point_rate)}"
                if charge.extra_points
                else (
                    f"{freight.billable_point_count} stops, "
                    f"within the {card.included_points} included"
                )
            ),
        )
    )

    if charge.unloading:
        points = unloading_detail(db, freight)
        articles = sum(a["quantity"] for p in points for a in p.articles)
        lines.append(
            MoneyLine(
                label="Unloading",
                amount=charge.unloading,
                working=(
                    f"{articles} {'article' if articles == 1 else 'articles'} across "
                    f"{len(points)} {'stop' if len(points) == 1 else 'stops'}, priced per "
                    "article and floor"
                ),
            )
        )
    if charge.coolie:
        lines.append(
            MoneyLine(
                label="Coolie, reimbursed",
                amount=charge.coolie,
                working="porter cash handed over at the points, recharged at cost",
            )
        )
    if charge.toll:
        lines.append(MoneyLine(label="Toll", amount=charge.toll, working="at cost"))
    if charge.detention:
        lines.append(MoneyLine(label="Detention", amount=charge.detention))

    return lines, charge.line_total, None


def _cost_from_payouts(db: Session, freight: Freight) -> tuple[list[MoneyLine], Decimal, str]:
    """What the trip actually paid, once the rows exist."""
    rows = (
        db.execute(select(FreightPayout).where(FreightPayout.freight_id == freight.id))
        .scalars()
        .all()
    )

    lines: list[MoneyLine] = []
    total = ZERO
    for row in rows:
        amount = Decimal(row.amount)
        total += amount
        lines.append(
            MoneyLine(
                label=_head_label(row.head, row.payee_type),
                amount=amount,
                working=row.basis or "",
            )
        )

    paid_to = str(rows[0].payee_type) if rows else "DRIVER"
    return lines, money(total), paid_to


def _head_label(head, payee_type) -> str:
    base = {
        ChargeHead.TRANSPORTATION: "Driving",
        ChargeHead.LOADING_UNLOADING: "Unloading",
        ChargeHead.POINT_INCENTIVE: "Point incentive",
    }.get(head, str(head).replace("_", " ").title())
    if str(payee_type) == str(PayeeType.VEHICLE_OWNER):
        return f"{base}, to the vehicle's owner"
    return base


def _cost_forecast(db: Session, freight: Freight) -> tuple[list[MoneyLine], Decimal, str]:
    """What the trip WOULD pay, on the terms in force. Before settlement."""
    lines: list[MoneyLine] = []
    total = ZERO
    paid_to = "DRIVER"

    for leg in freight.legs:
        vehicle = leg.vehicle
        if vehicle is None or leg.driver is None:
            continue

        payee = resolve_payee(vehicle.ownership)
        paid_to = str(payee)
        facts = leg_facts(db, leg)

        if payee == PayeeType.VEHICLE_OWNER:
            result = compute_leg_payout(
                vehicle.ownership,
                facts,
                hire_rates=resolve_hire_rates(db, vehicle.id, freight.trip_date),
            )
        else:
            result = compute_leg_payout(
                vehicle.ownership,
                facts,
                driver_rates=resolve_driver_rates(db, leg.driver_id, freight.trip_date),
            )

        for line in result.lines:
            total += line.amount
            lines.append(
                MoneyLine(
                    label=_head_label(line.head, line.payee_type),
                    amount=line.amount,
                    working=line.basis or "",
                )
            )

    return lines, money(total), paid_to


def freight_economics(db: Session, freight: Freight) -> FreightEconomics:
    """The whole trip: in, out, and what is left."""
    revenue, revenue_total, problem = _revenue(db, freight)

    settled = bool(
        db.scalar(select(FreightPayout.id).where(FreightPayout.freight_id == freight.id))
    )
    cost, cost_total, paid_to = (
        _cost_from_payouts(db, freight) if settled else _cost_forecast(db, freight)
    )

    # Road expenses the office has approved. Money out either way, and a trip
    # that looks profitable until you add the diesel is not a useful number.
    # Rejected ones are not costs, and pending ones are not yet decided.
    #
    # UNLOADING is excluded deliberately. The driver's delivery form writes an
    # expense row for the cash he handed over, and the payout above already
    # carries the same money under LOADING_UNLOADING — counting both would
    # charge the trip twice for one payment and make the margin look worse
    # than it is on exactly the trips that earn most.
    expenses = (
        db.execute(
            select(TripExpense).where(
                TripExpense.freight_id == freight.id,
                TripExpense.approval_status == ApprovalStatus.APPROVED,
                TripExpense.type != ExpenseType.UNLOADING,
            )
        )
        .scalars()
        .all()
    )
    for expense in expenses:
        amount = Decimal(expense.amount)
        cost_total += amount
        cost.append(
            MoneyLine(
                label=str(expense.type).replace("_", " ").title(),
                amount=amount,
                working="approved road expense"
                + (", recharged to the vendor" if expense.billable_to_vendor else ""),
                is_earning=False,
            )
        )

    first_leg: FreightLeg | None = freight.legs[0] if freight.legs else None
    vehicle = first_leg.vehicle if first_leg else None

    return FreightEconomics(
        trip_no=freight.trip_no,
        trip_date=freight.trip_date.isoformat(),
        status=str(freight.status),
        vehicle_no=vehicle.registration_no if vehicle else None,
        vehicle_type_name=(
            vehicle.vehicle_type.name if vehicle and vehicle.vehicle_type else None
        ),
        driver_name=first_leg.driver.name if first_leg and first_leg.driver else None,
        km=freight.total_km or freight.round_trip_km,
        points=freight.billable_point_count,
        revenue=revenue,
        revenue_total=money(revenue_total),
        revenue_problem=problem,
        cost=cost,
        cost_total=money(cost_total),
        paid_to=paid_to,
        is_settled=settled,
        unloading_points=unloading_detail(db, freight),
    )


def driver_earnings_for_leg(db: Session, leg: FreightLeg) -> tuple[list[MoneyLine], Decimal]:
    """What this leg pays the man who drove it, and how it was worked out.

    His side only. A driver on a rented vehicle is paid by the vehicle's
    owner, so the hire line is not his and does not appear — and nothing about
    what the vendor was charged appears either, because it is not his
    business and showing it invites an argument nobody needs on a lorry bay.
    """
    vehicle = leg.vehicle
    if vehicle is None or leg.driver is None:
        return [], ZERO

    facts = leg_facts(db, leg)
    if vehicle.ownership == VehicleOwnership.HIRED:
        result = compute_leg_payout(
            vehicle.ownership,
            facts,
            hire_rates=resolve_hire_rates(db, vehicle.id, leg.freight.trip_date),
        )
    else:
        result = compute_leg_payout(
            vehicle.ownership,
            facts,
            driver_rates=resolve_driver_rates(db, leg.driver_id, leg.freight.trip_date),
        )

    lines = [
        MoneyLine(
            label=_head_label(line.head, line.payee_type),
            amount=line.amount,
            working=line.basis or "",
        )
        for line in result.lines
        if line.payee_type == PayeeType.DRIVER
    ]
    return lines, result.total_for(PayeeType.DRIVER)
