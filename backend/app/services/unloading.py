"""Furniture unloading: priced per article, plus the climb.

Spare parts are not charged for unloading at all. Furniture is, and not by the
box - a chair, a wardrobe and a mattress are different work, and carrying any of
them up four floors is different work again:

    charge per article = base_rate + floors_charged x per_floor_rate
    point total        = sum over articles of (charge x quantity)

A chair at 50 with 10 a floor, delivered to the 4th floor, unloads at 90.

Ground floor is 0, so a ground-floor delivery is the base rate alone. Whether a
lift cancels the climb charge is a per-division commercial decision rather than
a fixed rule: wheeling a wardrobe into a lift is not the same job as carrying it
up four flights, but it is not the same as a ground-floor drop either.

Pure functions, like rating and payout, so the arithmetic is testable on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.rating import UnloadingItemRate
from app.services.rating import money


@dataclass(frozen=True)
class ItemRate:
    """One article's unloading price, lifted out of the ORM."""

    item_code: str
    item_name: str
    base_rate: Decimal
    per_floor_rate: Decimal = Decimal("0")
    charge_floors_with_lift: bool = False
    max_chargeable_floors: int = 0

    def floors_charged(self, floor_number: int, has_lift: bool) -> int:
        if floor_number <= 0:
            return 0
        if has_lift and not self.charge_floors_with_lift:
            return 0
        if self.max_chargeable_floors > 0:
            return min(floor_number, self.max_chargeable_floors)
        return floor_number

    def unit_charge(self, floor_number: int, has_lift: bool) -> Decimal:
        floors = self.floors_charged(floor_number, has_lift)
        return money(self.base_rate + Decimal(floors) * self.per_floor_rate)


@dataclass(frozen=True)
class UnloadItem:
    """What was actually carried in, per article type."""

    item_code: str
    quantity: int = 1


@dataclass
class UnloadingLine:
    item_code: str
    item_name: str
    quantity: int
    base_rate: Decimal
    floors_charged: int
    per_floor_rate: Decimal
    unit_charge: Decimal
    amount: Decimal
    basis: str


@dataclass
class PointUnloading:
    floor_number: int
    has_lift: bool
    lines: list[UnloadingLine] = field(default_factory=list)
    # Articles delivered with no rate on file. Billed as zero and surfaced, so
    # the gap is visible to the office rather than silently costing money.
    unpriced_item_codes: list[str] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return money(sum((line.amount for line in self.lines), Decimal("0")))

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines)


def calculate_point_unloading(
    rates: dict[str, ItemRate],
    items: list[UnloadItem],
    *,
    floor_number: int = 0,
    has_lift: bool = False,
) -> PointUnloading:
    """Price the unloading at one delivery point."""
    result = PointUnloading(floor_number=floor_number, has_lift=has_lift)

    for item in items:
        rate = rates.get(item.item_code)
        if rate is None:
            if item.item_code not in result.unpriced_item_codes:
                result.unpriced_item_codes.append(item.item_code)
            continue

        floors = rate.floors_charged(floor_number, has_lift)
        unit = rate.unit_charge(floor_number, has_lift)
        amount = money(unit * Decimal(item.quantity))

        if floors:
            basis = (
                f"{item.quantity} x {rate.item_name}: "
                f"{rate.base_rate} + {floors} floor(s) x {rate.per_floor_rate} "
                f"= {unit} each"
            )
        elif floor_number > 0 and has_lift:
            basis = (
                f"{item.quantity} x {rate.item_name}: {rate.base_rate} each "
                f"(floor {floor_number}, lift available so no climb charge)"
            )
        else:
            basis = f"{item.quantity} x {rate.item_name}: {rate.base_rate} each (ground floor)"

        result.lines.append(
            UnloadingLine(
                item_code=rate.item_code,
                item_name=rate.item_name,
                quantity=item.quantity,
                base_rate=money(rate.base_rate),
                floors_charged=floors,
                per_floor_rate=money(rate.per_floor_rate),
                unit_charge=unit,
                amount=amount,
                basis=basis,
            )
        )

    return result


def resolve_item_rates(
    db: Session, vendor_division_id, on_date: date
) -> dict[str, ItemRate]:
    """Every article rate in force for a division on a date, keyed by code."""
    rows = (
        db.execute(
            select(UnloadingItemRate)
            .where(
                UnloadingItemRate.vendor_division_id == vendor_division_id,
                UnloadingItemRate.is_active.is_(True),
                UnloadingItemRate.effective_from <= on_date,
                or_(
                    UnloadingItemRate.effective_to.is_(None),
                    UnloadingItemRate.effective_to >= on_date,
                ),
            )
            .order_by(UnloadingItemRate.effective_from.desc())
        )
        .scalars()
        .all()
    )

    # Newest effective row wins where a code has several versions.
    resolved: dict[str, ItemRate] = {}
    for row in rows:
        if row.item_code in resolved:
            continue
        resolved[row.item_code] = ItemRate(
            item_code=row.item_code,
            item_name=row.item_name,
            base_rate=Decimal(row.base_rate),
            per_floor_rate=Decimal(row.per_floor_rate),
            charge_floors_with_lift=bool(row.charge_floors_with_lift),
            max_chargeable_floors=int(row.max_chargeable_floors),
        )
    return resolved


def items_from_boxes(boxes) -> list[UnloadItem]:
    """Roll a point's boxes up into article counts.

    Furniture arrives as individual articles, so the boxes for a point are the
    articles; this only groups them by code so the invoice reads
    "4 x Chair" rather than four separate lines.
    """
    counts: dict[str, int] = {}
    for box in boxes:
        code = box.item_code
        if not code:
            continue
        counts[code] = counts.get(code, 0) + 1
    return [UnloadItem(item_code=code, quantity=qty) for code, qty in sorted(counts.items())]
