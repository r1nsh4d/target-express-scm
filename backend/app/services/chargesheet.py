"""The unloading charge sheet, one per delivery point.

Target Express already issues this on paper: a small printed form filled in at
the dealer's door — transporter, customer, the vendor's bill number, how many
items, which floor, what was carried, the amount, and a signature. It is what
the vendor's accounts team checks the unloading line of an invoice against,
and without it that line is a number with nothing behind it.

So the invoice gets its sheets attached. The freight lines say the vendor was
charged 4,200 for unloading across seven trips; the sheets behind them say
which dealer, which bill, which floor and which articles made up every rupee
of it. A query that used to mean ringing the driver is now a page.

WHAT IS STORED AND WHAT IS REBUILT

The quantities, the article names, the floor and the lift are facts recorded at
the door and stored on the point — they are never recomputed. `item_name` is
copied onto the row at the time precisely so a sheet reprinted next year says
what the driver was shown.

The per-article prices are resolved from the rates in force on the freight's
date, which is the same lookup that priced it in the first place. The TOTAL on
the sheet is the stored `unloading_billed`, not the sum of the rebuilt lines —
the stored figure is what the vendor was actually charged, and if the two ever
disagree the sheet says so rather than quietly printing a different number
from the invoice it is attached to.

COOLIE IS NOT UNLOADING
    It gets its own line, below the total, never inside it. A porter gang at a
    market gate is a cash demand the driver settled and the vendor reimburses;
    folding it into unloading is how "why has unloading gone up?" becomes
    unanswerable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.billing import VendorInvoice, VendorInvoiceLine
from app.models.consignment import Consignment
from app.models.freight import Freight, FreightPoint
from app.services.rating import money
from app.services.unloading import UnloadItem, calculate_point_unloading, resolve_item_rates


@dataclass
class SheetLine:
    """One article type carried in at this point."""

    item_code: str
    item_name: str
    quantity: int
    # What one of them cost at this floor, and why.
    base_rate: Decimal
    floors_charged: int
    per_floor_rate: Decimal
    unit_charge: Decimal
    amount: Decimal


@dataclass
class ChargeSheet:
    """One point's unloading, in the shape of the form the dealer signs."""

    point_id: str
    # Our side of the paperwork.
    trip_no: str
    lr_no: str | None
    trip_date: str
    vehicle_no: str
    # Theirs.
    customer_name: str
    location: str | None
    vendor_bill_nos: list[str]
    bill_date: str | None

    floor_number: int
    has_lift: bool
    lines: list[SheetLine] = field(default_factory=list)

    # What the vendor was actually charged, off the point. The sum of the
    # lines is `rebuilt_total`, and the two should agree.
    billed_total: Decimal = Decimal("0.00")
    rebuilt_total: Decimal = Decimal("0.00")
    # Articles carried that no rate card covers. Billed as nothing, so the gap
    # is money being given away and belongs on the screen.
    unpriced_item_codes: list[str] = field(default_factory=list)

    # Kept apart from unloading, always.
    coolie_billed: Decimal = Decimal("0.00")
    coolie_note: str | None = None

    # Who took delivery. The "approved by" of the paper form.
    receiver_name: str | None = None
    delivered_on: str | None = None

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines)

    @property
    def agrees_with_invoice(self) -> bool:
        """Does the working add up to what the vendor was charged?

        It can legitimately differ: an office correction to `unloading_billed`
        after the driver saved his sheet is a real thing people do. But a
        sheet that silently disagrees with the invoice it backs is worse than
        no sheet, so the difference is carried rather than hidden.
        """
        return self.billed_total == self.rebuilt_total


def sheet_for_point(db: Session, point: FreightPoint, freight: Freight) -> ChargeSheet | None:
    """Build one point's charge sheet, or None if nothing was unloaded.

    A point with no articles recorded and nothing billed has no sheet — an
    empty form attached to an invoice is noise, and on a spare-parts run every
    point would produce one.
    """
    items = [
        UnloadItem(item_code=row.item_code, quantity=row.quantity)
        for row in point.unloading_items
        if row.quantity > 0
    ]
    if not items and not point.unloading_billed and not point.coolie_billed:
        return None

    rates = resolve_item_rates(db, freight.vendor_division_id, freight.trip_date)
    priced = calculate_point_unloading(
        rates,
        items,
        floor_number=point.floor_number,
        has_lift=point.has_lift,
    )

    # The names on the point win over the names on the rate card. The rate card
    # is live and an article can be renamed; the point holds what the driver
    # was shown at the door.
    names = {row.item_code: row.item_name for row in point.unloading_items}

    consignments = (
        db.execute(
            select(Consignment)
            .where(Consignment.freight_point_id == point.id)
            .order_by(Consignment.vendor_bill_no)
        )
        .scalars()
        .all()
    )

    vehicle_no = next(
        (leg.vehicle.registration_no for leg in freight.legs if leg.vehicle is not None),
        "—",
    )

    return ChargeSheet(
        point_id=str(point.id),
        trip_no=freight.trip_no,
        lr_no=freight.lr_no,
        trip_date=freight.trip_date.isoformat(),
        vehicle_no=vehicle_no,
        customer_name=point.consignee.name if point.consignee else "—",
        location=point.address_snapshot
        or (point.consignee.city if point.consignee else None),
        vendor_bill_nos=[c.vendor_bill_no for c in consignments],
        bill_date=consignments[0].bill_date.isoformat() if consignments else None,
        floor_number=point.floor_number,
        has_lift=point.has_lift,
        lines=[
            SheetLine(
                item_code=line.item_code,
                item_name=names.get(line.item_code, line.item_name),
                quantity=line.quantity,
                base_rate=line.base_rate,
                floors_charged=line.floors_charged,
                per_floor_rate=line.per_floor_rate,
                unit_charge=line.unit_charge,
                amount=line.amount,
            )
            for line in priced.lines
        ],
        billed_total=money(Decimal(point.unloading_billed)),
        rebuilt_total=priced.total,
        unpriced_item_codes=priced.unpriced_item_codes,
        coolie_billed=money(Decimal(point.coolie_billed)),
        coolie_note=point.coolie_note,
        receiver_name=point.receiver_name,
        delivered_on=point.departed_at.date().isoformat() if point.departed_at else None,
    )


def _load_freights(db: Session, freight_ids: list) -> list[Freight]:
    if not freight_ids:
        return []
    return list(
        db.execute(
            select(Freight)
            .where(Freight.id.in_(freight_ids))
            .options(
                joinedload(Freight.points).joinedload(FreightPoint.unloading_items),
                joinedload(Freight.points).joinedload(FreightPoint.consignee),
                joinedload(Freight.legs),
            )
            .order_by(Freight.trip_date, Freight.trip_no)
        )
        .unique()
        .scalars()
        .all()
    )


def sheets_for_freights(db: Session, freight_ids: list) -> list[ChargeSheet]:
    """Every point's sheet across a set of freights, in delivery order."""
    sheets: list[ChargeSheet] = []
    for freight in _load_freights(db, freight_ids):
        for point in freight.points:
            sheet = sheet_for_point(db, point, freight)
            if sheet is not None:
                sheets.append(sheet)
    return sheets


def sheets_for_invoice(db: Session, invoice: VendorInvoice) -> list[ChargeSheet]:
    """The sheets backing one invoice's unloading.

    Driven off the invoice's own lines rather than off the period, because
    only some of a period's freights may have been billed — attaching a sheet
    for a freight that is not on the invoice is how a vendor is handed proof
    of a charge nobody made.
    """
    freight_ids = [
        line.freight_id
        for line in db.execute(
            select(VendorInvoiceLine)
            .where(VendorInvoiceLine.invoice_id == invoice.id)
            .order_by(VendorInvoiceLine.sl_no)
        )
        .scalars()
        .all()
    ]
    return sheets_for_freights(db, freight_ids)
