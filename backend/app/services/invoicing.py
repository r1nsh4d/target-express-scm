"""Turning finished freights into a vendor invoice.

The arithmetic lives in `services.rating`; this decides which freights belong on
an invoice, gathers what actually happened on each, and writes the lines.

Two rules it exists to enforce:

  * A freight is priced on the rate card in force ON ITS OWN DATE, not today's.
  * A freight can only be invoiced once. The line holds a unique key on the
    freight, so a double run is refused by the database rather than by a check
    somebody might forget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.billing import VendorInvoice, VendorInvoiceLine
from app.models.consignment import Box, Consignment
from app.models.enums import (
    ApprovalStatus,
    ExpenseType,
    FreightStatus,
    InvoiceStatus,
    UnloadingBasis,
)
from app.models.expense import TripExpense
from app.models.freight import Freight
from app.models.vendor import VendorDivision
from app.services.rating import (
    FreightCharge,
    RateCardNotFound,
    RateTerms,
    TripFacts,
    calculate_freight_charge,
    money,
    resolve_rate_card,
)
from app.services.unloading import calculate_point_unloading, items_from_boxes, resolve_item_rates


@dataclass
class PricedFreight:
    freight: Freight
    charge: FreightCharge
    vehicle_no: str
    toll: Decimal
    detention: Decimal
    unloading: Decimal
    coolie: Decimal


def _pass_through(db: Session, freight_id, kind: ExpenseType) -> Decimal:
    """Tolls and detention are billed at what was actually paid, once approved."""
    rows = (
        db.execute(
            select(TripExpense).where(
                TripExpense.freight_id == freight_id,
                TripExpense.type == kind,
                TripExpense.billable_to_vendor.is_(True),
                TripExpense.approval_status != ApprovalStatus.REJECTED,
            )
        )
        .scalars()
        .all()
    )
    return money(sum((Decimal(r.amount) for r in rows), Decimal("0")))


def billable_unloading(db: Session, freight: Freight, card) -> Decimal:
    """What the vendor is charged for unloading on this freight.

    Not what was paid out - that is the driver's side, and the two are
    deliberately independent.
    """
    basis = card.unloading_basis

    if basis == UnloadingBasis.NOT_APPLICABLE:
        return Decimal("0.00")

    if basis == UnloadingBasis.ACTUAL:
        return money(sum((Decimal(p.unloading_paid) for p in freight.points), Decimal("0")))

    if basis == UnloadingBasis.PER_POINT:
        return money(Decimal(freight.billable_point_count) * Decimal(card.unloading_rate))

    if basis == UnloadingBasis.PER_BOX:
        boxes = sum(p.delivered_box_count or p.loaded_box_count for p in freight.points)
        return money(Decimal(boxes) * Decimal(card.unloading_rate))

    if basis == UnloadingBasis.PER_ITEM_FLOOR:
        # Furniture: each article has a ground-floor rate plus a climb charge.
        rates = resolve_item_rates(db, freight.vendor_division_id, freight.trip_date)
        total = Decimal("0")
        for point in freight.points:
            boxes = (
                db.execute(
                    select(Box)
                    .join(Consignment, Box.consignment_id == Consignment.id)
                    .where(Consignment.freight_point_id == point.id)
                )
                .scalars()
                .all()
            )
            result = calculate_point_unloading(
                rates,
                items_from_boxes(boxes),
                floor_number=point.floor_number,
                has_lift=point.has_lift,
            )
            total += result.total
        return money(total)

    return Decimal("0.00")


def billable_coolie(freight: Freight) -> Decimal:
    """What the vendor is reimbursing in coolie money across the whole run.

    Reads `coolie_billed`, not `coolie_paid`. The driver may have handed over
    more than the vendor agreed to cover - at an unfamiliar market that happens -
    and the difference is Target Express's to absorb or to argue, not something
    to put on an invoice by default.
    """
    return money(sum((p.coolie_billed or Decimal("0")) for p in freight.points))


def price_freight(db: Session, freight: Freight) -> PricedFreight:
    """Work out what one freight bills, on the card in force on its date."""
    leg = freight.legs[0] if freight.legs else None
    vehicle_type_id = leg.vehicle.vehicle_type_id if leg and leg.vehicle else None

    card = resolve_rate_card(db, freight.vendor_division_id, freight.trip_date, vehicle_type_id)

    toll = _pass_through(db, freight.id, ExpenseType.TOLL)
    detention = _pass_through(db, freight.id, ExpenseType.DETENTION)
    unloading = billable_unloading(db, freight, card)
    coolie = billable_coolie(freight)

    charge = calculate_freight_charge(
        RateTerms.from_rate_card(card),
        TripFacts(
            km=freight.total_km or freight.round_trip_km,
            points=freight.billable_point_count,
            toll=toll,
            unloading=unloading,
            detention=detention,
            coolie=coolie,
        ),
    )

    return PricedFreight(
        freight=freight,
        charge=charge,
        vehicle_no=leg.vehicle.registration_no if leg and leg.vehicle else "—",
        toll=toll,
        detention=detention,
        unloading=unloading,
        coolie=coolie,
    )


def invoiceable_freights(
    db: Session, vendor_division_id, period_from: date, period_to: date
) -> list[Freight]:
    """Completed freights in the period that have not been billed yet."""
    already = select(VendorInvoiceLine.freight_id)
    return list(
        db.execute(
            select(Freight)
            .where(
                Freight.vendor_division_id == vendor_division_id,
                Freight.trip_date >= period_from,
                Freight.trip_date <= period_to,
                Freight.status == FreightStatus.COMPLETED,
                Freight.id.notin_(already),
            )
            .order_by(Freight.trip_date, Freight.trip_no)
        )
        .scalars()
        .all()
    )


def price_period(
    db: Session, vendor_division_id, period_from: date, period_to: date
) -> tuple[list[PricedFreight], list[str]]:
    """Price everything invoiceable in the period.

    Returns the priced freights and, separately, the ones that could not be
    priced - a freight whose date falls outside every rate card is surfaced
    rather than silently dropped from the invoice.
    """
    priced: list[PricedFreight] = []
    problems: list[str] = []

    for freight in invoiceable_freights(db, vendor_division_id, period_from, period_to):
        try:
            priced.append(price_freight(db, freight))
        except RateCardNotFound:
            problems.append(
                f"{freight.trip_no} ({freight.trip_date}): no rate card covers this date"
            )

    return priced, problems


def next_invoice_no(db: Session, division: VendorDivision, on: date) -> str:
    """Series / financial year / serial, matching the format already in use."""
    fy_start = on.year if on.month >= 4 else on.year - 1
    fy = f"{fy_start}-{str(fy_start + 1)[-2:]}"
    prefix = f"{division.invoice_series}/{fy}/"

    used = db.scalar(
        select(func.count())
        .select_from(VendorInvoice)
        .where(VendorInvoice.invoice_no.like(f"{prefix}%"))
    )
    return f"{prefix}{(used or 0) + 1:03d}"


def create_invoice(
    db: Session,
    division: VendorDivision,
    period_from: date,
    period_to: date,
    invoice_date: date,
    issued_by_id=None,
) -> VendorInvoice:
    priced, problems = price_period(db, division.id, period_from, period_to)

    if problems:
        raise ValueError("; ".join(problems))
    if not priced:
        raise ValueError("No completed, uninvoiced freights in that period")

    taxable = money(sum((p.charge.line_total for p in priced), Decimal("0")))
    gst_rate = Decimal(division.gst_rate_percent or 0)
    gst_total = money(taxable * gst_rate / Decimal("100"))
    half = money(gst_total / Decimal("2"))

    invoice = VendorInvoice(
        invoice_no=next_invoice_no(db, division, invoice_date),
        invoice_date=invoice_date,
        period_from=period_from,
        period_to=period_to,
        vendor_division_id=division.id,
        vehicle_type_label=None,
        taxable_value=taxable,
        # Intra-state by default. Place-of-supply handling is a later refinement;
        # both Godrej divisions are Kerala-to-Kerala today.
        cgst=half,
        sgst=money(gst_total - half),
        igst=Decimal("0.00"),
        total=money(taxable + gst_total),
        status=InvoiceStatus.DRAFT,
        issued_by_id=issued_by_id,
    )
    db.add(invoice)
    db.flush()

    for i, p in enumerate(priced, start=1):
        c = p.charge
        db.add(
            VendorInvoiceLine(
                invoice_id=invoice.id,
                freight_id=p.freight.id,
                sl_no=i,
                trip_date=p.freight.trip_date,
                trip_no=p.freight.trip_no,
                lr_no=p.freight.lr_no,
                vehicle_no=p.vehicle_no,
                destination_text=p.freight.destination_text or "—",
                point_count=p.freight.billable_point_count,
                start_km=p.freight.legs[0].start_odometer if p.freight.legs else None,
                close_km=p.freight.legs[-1].end_odometer if p.freight.legs else None,
                km=p.freight.total_km or p.freight.round_trip_km,
                base_amount=c.base_amount,
                included_km=c.included_km,
                extra_km=c.extra_km,
                extra_km_rate=c.extra_km_rate,
                extra_km_amount=c.extra_km_amount,
                included_points=c.included_points,
                extra_points=c.extra_points,
                extra_point_rate=c.extra_point_rate,
                extra_point_amount=c.extra_point_amount,
                toll=c.toll,
                unloading=c.unloading,
                unloading_additional=c.unloading_additional,
                detention=c.detention,
                coolie=c.coolie,
                line_total=c.line_total,
            )
        )
        p.freight.status = FreightStatus.BILLED

    db.flush()
    return invoice
