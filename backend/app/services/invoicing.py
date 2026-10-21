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
from app.services.odometer import MAX_LEG_KM
from app.services.rating import (
    FreightCharge,
    RateCardNotFound,
    RateTerms,
    TripFacts,
    calculate_freight_charge,
    money,
    resolve_rate_card,
)
from app.services.unloading import (
    UnloadItem,
    calculate_point_unloading,
    items_from_boxes,
    resolve_item_rates,
)


@dataclass
class PricedFreight:
    freight: Freight
    charge: FreightCharge
    vehicle_no: str
    # "Dost", "Ace". The printed invoice bills a freight charge per type.
    vehicle_type: str | None
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
            total += _point_unloading(db, point, rates).total
        return money(total)

    return Decimal("0.00")


def _point_unloading(db: Session, point, rates):
    """Price one stop's unloading, preferring what the driver logged.

    Two sources, and the order matters.

    What the DRIVER logged at the door is what actually happened: he stood
    there and carried it in. The bill says five chairs; four came off the
    lorry and one was refused, and only he knows that.

    The BOXES on the bill are the fallback, for a stop where nobody logged
    anything — an older trip, or a driver who did not fill it in. Charging
    zero because a man forgot is worse than charging from the paperwork, and
    the paperwork is usually right.

    It is never a mixture. A stop that has a log is priced entirely from the
    log, including a log that says a single chair, because "he logged less than
    the bill" is the case this exists to capture and topping it up from the
    boxes would throw that away.
    """
    logged = [
        UnloadItem(item_code=row.item_code, quantity=row.quantity)
        for row in point.unloading_items
        if row.quantity > 0
    ]

    if logged:
        items = logged
    else:
        boxes = (
            db.execute(
                select(Box)
                .join(Consignment, Box.consignment_id == Consignment.id)
                .where(Consignment.freight_point_id == point.id)
            )
            .scalars()
            .all()
        )
        items = items_from_boxes(boxes)

    return calculate_point_unloading(
        rates,
        items,
        floor_number=point.floor_number,
        has_lift=point.has_lift,
    )


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
        vehicle_type=(
            leg.vehicle.vehicle_type.name
            if leg and leg.vehicle and leg.vehicle.vehicle_type
            else None
        ),
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
            continue

        # A distance that cannot be a round trip, left OFF the invoice.
        #
        # An invoice for ₹34,28,434.24 went to the vendor on a single
        # one-point run to Aluva, because 180,015 — the lorry's odometer —
        # had been entered as the leg's distance. The readings are guarded
        # now, but the freights already carrying a bad figure are still in
        # the database, and the next sweep would bill them exactly as the
        # first one did.
        #
        # Refused rather than flagged, because a warning above a tick box
        # that is already ticked is a warning somebody clicks past. The trip
        # comes back the moment its odometer is corrected.
        km = freight.total_km or freight.round_trip_km
        if km > MAX_LEG_KM:
            priced.pop()
            problems.append(
                f"{freight.trip_no} ({freight.trip_date}): {km:,} km is not a round "
                "trip — the odometer looks wrong. Correct it on the freight and this "
                "will bill normally."
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


def price_chosen(
    db: Session, vendor_division_id, freight_ids: list
) -> tuple[list[PricedFreight], list[str]]:
    """Price exactly these freights, in trip order.

    The period sweep takes everything finished between two dates, which is the
    right default and the wrong thing when one freight is disputed, or is
    waiting on a toll receipt, or simply belongs on next month's bill. Naming
    the freights is how a bill gets raised for some of the work and not the
    rest.

    Anything that cannot go on an invoice is reported rather than quietly
    dropped: billing four freights when five were ticked, and saying nothing,
    is how work goes missing.
    """
    priced: list[PricedFreight] = []
    problems: list[str] = []
    seen: set = set()

    for freight_id in freight_ids:
        freight = db.get(Freight, freight_id)

        if freight is None:
            problems.append(f"{freight_id}: no such freight")
            continue
        if freight.id in seen:
            continue
        seen.add(freight.id)

        if freight.vendor_division_id != vendor_division_id:
            problems.append(f"{freight.trip_no}: belongs to a different vendor division")
            continue
        # Asked before the status check, and deliberately. A freight that has
        # been invoiced is BILLED, so the status check would catch it first and
        # answer "only a completed freight can be billed" — which is true,
        # unhelpful, and sends somebody looking for a trip that never finished
        # when the real answer is that it is already on invoice.
        billed = db.scalar(
            select(func.count())
            .select_from(VendorInvoiceLine)
            .where(VendorInvoiceLine.freight_id == freight.id)
        )
        if billed:
            problems.append(f"{freight.trip_no}: is already on an invoice")
            continue

        if freight.status != FreightStatus.COMPLETED:
            problems.append(
                f"{freight.trip_no}: is {freight.status}, and only a completed freight "
                "can be billed"
            )
            continue

        try:
            priced.append(price_freight(db, freight))
        except RateCardNotFound:
            problems.append(
                f"{freight.trip_no} ({freight.trip_date}): no rate card covers this date"
            )

    priced.sort(key=lambda p: (p.freight.trip_date, p.freight.trip_no))
    return priced, problems


def create_invoice(
    db: Session,
    division: VendorDivision,
    period_from: date,
    period_to: date,
    invoice_date: date,
    issued_by_id=None,
    freight_ids: list | None = None,
) -> VendorInvoice:
    """Raise an invoice, either for a period or for named freights.

    With `freight_ids`, the period printed on the document is derived from the
    freights actually on it rather than from whatever dates were typed. An
    invoice that says "01 Aug to 07 Oct" but carries two trips from September
    invites the question of what happened to the rest.
    """
    if freight_ids is not None:
        if not freight_ids:
            raise ValueError("No freights were selected")
        priced, problems = price_chosen(db, division.id, freight_ids)
    else:
        priced, problems = price_period(db, division.id, period_from, period_to)

    if problems:
        raise ValueError("; ".join(problems))
    if not priced:
        raise ValueError("No completed, uninvoiced freights in that period")

    if freight_ids is not None:
        period_from = min(p.freight.trip_date for p in priced)
        period_to = max(p.freight.trip_date for p in priced)

    # What is taxed, and what is only passed on.
    #
    # The vendor's own tax summary splits the month into 1,56,382 at 2.5% +
    # 2.5% and 2,150 at nil, and the 2,150 is exactly the toll: cash handed to
    # a booth and recharged at cost, not a service supplied. We were taxing
    # it, so every invoice we raised was a little higher than the one their
    # accountant would have raised for the same work.
    #
    # Toll alone, deliberately — not every reimbursement. Coolie is recharged
    # at cost too, and their document taxes it. Matching the document they
    # already send beats being clever about it.
    gross = money(sum((p.charge.line_total for p in priced), Decimal("0")))
    zero_rated = money(sum((p.toll for p in priced), Decimal("0")))
    taxable = money(gross - zero_rated)

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
        zero_rated_value=zero_rated,
        # Frozen here rather than read off the division at print time, so a
        # rate changed next year does not re-rate what was sent this one.
        gst_rate_percent=gst_rate,
        # Intra-state by default. Place-of-supply handling is a later refinement;
        # both Godrej divisions are Kerala-to-Kerala today.
        cgst=half,
        sgst=money(gst_total - half),
        igst=Decimal("0.00"),
        total=money(gross + gst_total),
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
                vehicle_type=p.vehicle_type,
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
