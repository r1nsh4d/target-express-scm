"""Money out of the business (vendor invoices) and money out to people
(driver and vehicle-owner settlements)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import ACCOUNTS_ROLES, BACK_OFFICE_ROLES, require_roles
from app.api.routes.company import amount_in_words
from app.db.session import get_db
from app.models.billing import VendorInvoice
from app.models.enums import (
    AdvanceStatus,
    FreightStatus,
    InvoiceStatus,
    PayeeType,
    SettlementStatus,
)
from app.models.fleet import Driver, VehicleOwner
from app.models.freight import Freight
from app.models.settlement import Advance, FreightPayout, Settlement
from app.models.user import User
from app.models.vendor import VendorDivision
from app.schemas.base import ORMModel
from app.services.invoicing import create_invoice, price_period
from app.services.rating import money

router = APIRouter(prefix="/api", tags=["billing"])

ReadDep = Depends(require_roles(*BACK_OFFICE_ROLES))
MoneyDep = Depends(require_roles(*ACCOUNTS_ROLES))


# --------------------------------------------------------------------------- #
# Vendor invoices                                                             #
# --------------------------------------------------------------------------- #

class PeriodIn(BaseModel):
    vendor_division_id: str
    period_from: date
    period_to: date
    invoice_date: date | None = None
    # When given, ONLY these freights go on the invoice and the rest of the
    # period is left alone. The period is still sent, because it is what the
    # preview was built from and what the screen shows.
    freight_ids: list[str] | None = None


class PreviewLine(BaseModel):
    # So the screen can tick individual freights and bill only those.
    freight_id: str
    trip_no: str
    lr_no: str | None
    trip_date: date
    vehicle_no: str
    destination_text: str | None
    point_count: int
    km: int
    base_amount: Decimal
    extra_km_amount: Decimal
    extra_point_amount: Decimal
    toll: Decimal
    unloading: Decimal
    detention: Decimal
    # Its own column, never added into `unloading`. A vendor querying why
    # unloading rose has to be able to see the two apart.
    coolie: Decimal
    line_total: Decimal


class PreviewOut(BaseModel):
    vendor_division_name: str
    period_from: date
    period_to: date
    freight_count: int
    lines: list[PreviewLine]
    taxable_value: Decimal
    gst_rate_percent: Decimal
    gst_amount: Decimal
    total: Decimal
    # Freights that fall outside every rate card, surfaced rather than dropped.
    problems: list[str]


class InvoiceRowOut(ORMModel):
    id: str
    invoice_no: str
    invoice_date: date
    period_from: date
    period_to: date
    vendor_division_id: str
    vendor_division_name: str | None = None
    taxable_value: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal
    status: InvoiceStatus
    line_count: int = 0
    # Present once a payment has been recorded.
    paid_on: date | None = None
    amount_received: Decimal | None = None
    payment_mode: str | None = None
    payment_reference: str | None = None


class InvoiceLineOut(ORMModel):
    id: str
    sl_no: int
    trip_date: date
    trip_no: str
    lr_no: str | None
    vehicle_no: str
    destination_text: str
    point_count: int
    start_km: int | None
    close_km: int | None
    km: int
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


class InvoiceOut(InvoiceRowOut):
    lines: list[InvoiceLineOut] = []
    # Everything the printed document needs that the list does not.
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    vendor_billing_address: str | None = None
    division_gstin: str | None = None
    place_of_supply_state_code: str | None = None
    # A tax invoice states the total in words as well as figures, and the
    # vendor's accounts team reads the words to check the figure.
    total_in_words: str = ""


@router.post("/invoices/preview", response_model=PreviewOut)
def preview_invoice(payload: PeriodIn, db: Session = Depends(get_db), _=MoneyDep):
    """What an invoice for this period would look like, without creating it."""
    division = db.get(VendorDivision, payload.vendor_division_id)
    if division is None:
        raise HTTPException(status_code=404, detail="Vendor division not found")

    priced, problems = price_period(
        db, division.id, payload.period_from, payload.period_to
    )

    taxable = money(sum((p.charge.line_total for p in priced), Decimal("0")))
    gst_rate = Decimal(division.gst_rate_percent or 0)
    gst = money(taxable * gst_rate / Decimal("100"))

    return PreviewOut(
        vendor_division_name=division.name,
        period_from=payload.period_from,
        period_to=payload.period_to,
        freight_count=len(priced),
        lines=[
            PreviewLine(
                freight_id=str(p.freight.id),
                trip_no=p.freight.trip_no,
                lr_no=p.freight.lr_no,
                trip_date=p.freight.trip_date,
                vehicle_no=p.vehicle_no,
                destination_text=p.freight.destination_text,
                point_count=p.freight.billable_point_count,
                km=p.freight.total_km or p.freight.round_trip_km,
                base_amount=p.charge.base_amount,
                extra_km_amount=p.charge.extra_km_amount,
                extra_point_amount=p.charge.extra_point_amount,
                toll=p.charge.toll,
                unloading=p.charge.unloading,
                detention=p.charge.detention,
                coolie=p.charge.coolie,
                line_total=p.charge.line_total,
            )
            for p in priced
        ],
        taxable_value=taxable,
        gst_rate_percent=gst_rate,
        gst_amount=gst,
        total=money(taxable + gst),
        problems=problems,
    )


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def generate_invoice(payload: PeriodIn, db: Session = Depends(get_db), user: User = MoneyDep):
    division = db.get(VendorDivision, payload.vendor_division_id)
    if division is None:
        raise HTTPException(status_code=404, detail="Vendor division not found")

    try:
        invoice = create_invoice(
            db,
            division,
            payload.period_from,
            payload.period_to,
            payload.invoice_date or date.today(),
            issued_by_id=user.id,
            freight_ids=payload.freight_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    db.commit()
    db.refresh(invoice)
    return _invoice_out(invoice, with_lines=True)


def _invoice_out(inv: VendorInvoice, with_lines: bool = False) -> InvoiceOut:
    out = InvoiceOut.model_validate(inv)
    division = inv.vendor_division
    out.vendor_division_name = division.name if division else None
    out.line_count = len(inv.lines)
    out.lines = (
        [InvoiceLineOut.model_validate(line) for line in inv.lines] if with_lines else []
    )

    # The printed document needs who it is addressed to, and under which GSTIN.
    # A division carries its own where it has one, because Godrej's divisions
    # bill separately; otherwise it falls back to the vendor's.
    if division is not None:
        out.division_gstin = division.gstin
        out.place_of_supply_state_code = division.place_of_supply_state_code
        out.vendor_billing_address = division.billing_address
        vendor = division.vendor
        if vendor is not None:
            out.vendor_name = vendor.name
            out.vendor_gstin = division.gstin or vendor.gstin
            out.vendor_billing_address = division.billing_address or vendor.billing_address

    out.total_in_words = amount_in_words(Decimal(inv.total or 0))
    return out


@router.get("/invoices", response_model=list[InvoiceRowOut])
def list_invoices(
    vendor_division_id: str | None = None,
    db: Session = Depends(get_db),
    _=ReadDep,
):
    stmt = (
        select(VendorInvoice)
        .options(joinedload(VendorInvoice.lines), joinedload(VendorInvoice.vendor_division))
        .order_by(VendorInvoice.invoice_date.desc())
    )
    if vendor_division_id:
        stmt = stmt.where(VendorInvoice.vendor_division_id == vendor_division_id)

    rows = db.execute(stmt).unique().scalars().all()
    return [_invoice_out(i) for i in rows]


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: str, db: Session = Depends(get_db), _=ReadDep):
    invoice = db.get(VendorInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _invoice_out(invoice, with_lines=True)


class InvoiceStatusIn(BaseModel):
    status: InvoiceStatus


class PaymentIn(BaseModel):
    paid_on: date | None = None
    # Left out means "the whole invoice". Given, it is what the bank actually
    # credited, which after a TDS deduction is less than the invoice total.
    amount_received: Decimal | None = None
    payment_mode: str | None = Field(default=None, max_length=24)
    payment_reference: str | None = Field(default=None, max_length=120)


class MoneyInRow(BaseModel):
    invoice_id: str
    invoice_no: str
    vendor_division_name: str | None
    invoice_date: date
    paid_on: date
    invoiced: Decimal
    received: Decimal
    # invoiced - received. Usually TDS; occasionally a short payment that needs
    # chasing. Either way it is a number somebody has to account for, so it is
    # shown rather than left to be worked out.
    shortfall: Decimal
    payment_mode: str | None
    payment_reference: str | None


@router.patch("/invoices/{invoice_id}", response_model=InvoiceRowOut)
def set_invoice_status(
    invoice_id: str, payload: InvoiceStatusIn, db: Session = Depends(get_db), _=MoneyDep
):
    invoice = db.get(VendorInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    # Moving off PAID un-records the receipt. An invoice that is no longer paid
    # but still carries a payment date would keep showing up under money in,
    # and the bank reconciliation would never balance.
    if invoice.status == InvoiceStatus.PAID and payload.status != InvoiceStatus.PAID:
        invoice.paid_on = None
        invoice.amount_received = None
        invoice.payment_mode = None
        invoice.payment_reference = None

    invoice.status = payload.status

    # Marked paid with no detail: assume today and the full amount, so the
    # one-button path still produces a receipt that can be reconciled.
    if payload.status == InvoiceStatus.PAID and invoice.paid_on is None:
        invoice.paid_on = date.today()
        invoice.amount_received = invoice.total

    db.commit()
    db.refresh(invoice)
    return _invoice_out(invoice)


@router.post("/invoices/{invoice_id}/payment", response_model=InvoiceRowOut)
def record_payment(
    invoice_id: str, payload: PaymentIn, db: Session = Depends(get_db), _=MoneyDep
):
    """Record what the vendor actually paid, and mark the invoice paid.

    Separate from the status flip because a payment is four facts, not one. The
    one that matters is the amount: transport vendors deduct TDS at source, so
    a 92,478.40 invoice is settled by 91,553.62 and the balance arrives later as
    a credit. Recording the invoice total as the receipt would overstate money
    in and leave the bank reconciliation short with nothing to explain it.

    A draft cannot be paid. Money against a document that was never issued is
    either the wrong invoice or a receipt that belongs somewhere else.
    """
    invoice = db.get(VendorInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == InvoiceStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{invoice.invoice_no} is still a draft. Issue it before recording a "
                "payment against it."
            ),
        )
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(
            status_code=409, detail=f"{invoice.invoice_no} was cancelled."
        )

    received = (
        money(payload.amount_received)
        if payload.amount_received is not None
        else Decimal(invoice.total or 0)
    )
    if received <= 0:
        raise HTTPException(status_code=422, detail="A receipt has to be more than zero.")
    if received > Decimal(invoice.total or 0):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{received} is more than the invoice total of {invoice.total}. "
                "Check the figure — an overpayment is not recorded here."
            ),
        )

    invoice.paid_on = payload.paid_on or date.today()
    invoice.amount_received = received
    invoice.payment_mode = payload.payment_mode
    invoice.payment_reference = payload.payment_reference
    invoice.status = InvoiceStatus.PAID

    db.commit()
    db.refresh(invoice)
    return _invoice_out(invoice)


@router.get("/money-in", response_model=list[MoneyInRow])
def money_in(
    period_from: date | None = None,
    period_to: date | None = None,
    db: Session = Depends(get_db),
    _=MoneyDep,
):
    """Payments received, newest first.

    The other side of Settlements, which is money going out. Reads from the
    invoices themselves rather than a separate ledger, so a receipt cannot
    disagree with the document it was paid against.
    """
    stmt = (
        select(VendorInvoice)
        .options(joinedload(VendorInvoice.vendor_division))
        .where(VendorInvoice.status == InvoiceStatus.PAID, VendorInvoice.paid_on.isnot(None))
        # id breaks the tie, or two payments on the same day swap places between
        # one refresh and the next.
        .order_by(VendorInvoice.paid_on.desc(), VendorInvoice.id)
    )
    if period_from:
        stmt = stmt.where(VendorInvoice.paid_on >= period_from)
    if period_to:
        stmt = stmt.where(VendorInvoice.paid_on <= period_to)

    rows = db.execute(stmt).unique().scalars().all()
    return [
        MoneyInRow(
            invoice_id=str(inv.id),
            invoice_no=inv.invoice_no,
            vendor_division_name=inv.vendor_division.name if inv.vendor_division else None,
            invoice_date=inv.invoice_date,
            paid_on=inv.paid_on,
            invoiced=Decimal(inv.total or 0),
            received=Decimal(inv.amount_received or 0),
            shortfall=money(Decimal(inv.total or 0) - Decimal(inv.amount_received or 0)),
            payment_mode=inv.payment_mode,
            payment_reference=inv.payment_reference,
        )
        for inv in rows
    ]


class BillFreightIn(BaseModel):
    invoice_date: date | None = None


@router.post("/freights/{freight_id}/bill", response_model=InvoiceOut, status_code=201)
def bill_one_freight(
    freight_id: str,
    payload: BillFreightIn,
    db: Session = Depends(get_db),
    user: User = MoneyDep,
):
    """Raise an invoice for this freight alone.

    BILLED is not a status anybody sets by hand — it follows from issuing an
    invoice, so that a freight marked billed always has a document behind it.
    That rule is right, but it left no way to bill one trip: you had to go to
    Invoices, choose the division, and narrow a date range until it happened to
    contain exactly the trip you wanted.

    So the rule stays and the route gets shorter. This is the same code path as
    the period run, given one freight.
    """
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise HTTPException(status_code=404, detail="Freight not found")

    division = db.get(VendorDivision, freight.vendor_division_id)
    if division is None:
        raise HTTPException(status_code=404, detail="Vendor division not found")

    try:
        invoice = create_invoice(
            db,
            division,
            freight.trip_date,
            freight.trip_date,
            payload.invoice_date or date.today(),
            issued_by_id=user.id,
            freight_ids=[freight.id],
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    db.commit()
    db.refresh(invoice)
    return _invoice_out(invoice, with_lines=True)


@router.delete("/invoices/{invoice_id}/lines/{line_id}", response_model=InvoiceOut)
def remove_invoice_line(
    invoice_id: str, line_id: str, db: Session = Depends(get_db), _=MoneyDep
):
    """Take one freight off a draft and re-add up what is left.

    The alternative when a draft is nearly right is to discard the whole thing
    and generate again, which means re-ticking every other freight on it. A
    trip that turns out to be disputed, or is waiting on a toll receipt, comes
    off on its own.

    The freight goes back to COMPLETED, so it appears on the next run rather
    than disappearing. The last line cannot be removed — an invoice with no
    lines is not a document, it is a number with a total of zero, and it should
    be discarded instead.
    """
    invoice = db.get(VendorInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail=f"{invoice.invoice_no} is {invoice.status}. Only a draft can be edited.",
        )

    line = next((ln for ln in invoice.lines if str(ln.id) == line_id), None)
    if line is None:
        raise HTTPException(status_code=404, detail="That line is not on this invoice")

    if len(invoice.lines) == 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "That is the only freight on this invoice. Discard the draft instead "
                "of emptying it."
            ),
        )

    freight = db.get(Freight, line.freight_id)
    if freight is not None and freight.status == FreightStatus.BILLED:
        freight.status = FreightStatus.COMPLETED

    invoice.lines.remove(line)
    db.flush()
    _recompute(db, invoice)
    db.commit()
    db.refresh(invoice)
    return _invoice_out(invoice, with_lines=True)


def _recompute(db: Session, invoice: VendorInvoice) -> None:
    """Re-add the totals, the tax and the serial numbers after a line changes.

    Leaving the stored total behind after dropping a line would print a
    document whose lines do not sum to its total — the single thing a vendor's
    accounts team is certain to notice.
    """
    lines = sorted(invoice.lines, key=lambda ln: (ln.trip_date, ln.trip_no))
    for i, line in enumerate(lines, start=1):
        line.sl_no = i

    taxable = money(sum((ln.line_total for ln in lines), Decimal("0")))
    division = invoice.vendor_division
    gst_rate = Decimal(division.gst_rate_percent or 0) if division else Decimal("0")
    gst_total = money(taxable * gst_rate / Decimal("100"))

    invoice.taxable_value = taxable
    # Which heads the tax sits under was decided when the invoice was raised;
    # recomputing must not silently move an inter-state bill to CGST+SGST.
    if invoice.igst and invoice.igst > 0:
        invoice.igst = gst_total
        invoice.cgst = Decimal("0.00")
        invoice.sgst = Decimal("0.00")
    else:
        half = money(gst_total / Decimal("2"))
        invoice.cgst = half
        invoice.sgst = money(gst_total - half)
        invoice.igst = Decimal("0.00")

    invoice.total = money(taxable + gst_total)

    # The period on the document follows the work on it.
    if lines:
        invoice.period_from = min(ln.trip_date for ln in lines)
        invoice.period_to = max(ln.trip_date for ln in lines)

    db.flush()


@router.delete("/invoices/{invoice_id}", status_code=204)
def discard_invoice(invoice_id: str, db: Session = Depends(get_db), _=MoneyDep):
    """Throw away a draft and give its freights back.

    Generating an invoice is one button and it sweeps up every completed
    freight in the period. Pick the wrong division, or a period a week too
    wide, and the mistake was permanent: the freights were already flipped to
    BILLED, which is the one status an admin may not set by hand, so they could
    not be put back and could not be invoiced again. The only repair was to
    issue a document nobody wanted, or edit the database.

    So a DRAFT can be discarded. Its freights go back to COMPLETED and are
    available to the next run.

    Only a DRAFT. Once an invoice is ISSUED it has a number the vendor has
    seen, and a tax invoice that has left the building is cancelled, not
    deleted — the number must stay in the series or the series has a hole in
    it, which is exactly what an auditor looks for.
    """
    invoice = db.get(VendorInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{invoice.invoice_no} is {invoice.status}, not a draft. An invoice "
                "the vendor has already seen is cancelled, not deleted — its number "
                "has to stay in the series."
            ),
        )

    # Hand the freights back, or they stay BILLED against an invoice that no
    # longer exists and can never be billed again.
    released = 0
    for line in invoice.lines:
        freight = db.get(Freight, line.freight_id)
        if freight is not None and freight.status == FreightStatus.BILLED:
            freight.status = FreightStatus.COMPLETED
            released += 1

    db.delete(invoice)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Settlements                                                                 #
# --------------------------------------------------------------------------- #

class PendingPayeeOut(BaseModel):
    payee_type: PayeeType
    payee_id: str
    payee_name: str
    freight_count: int
    by_head: dict[str, Decimal]
    gross: Decimal
    advance_outstanding: Decimal
    net_payable: Decimal


class SettlementIn(BaseModel):
    payee_type: PayeeType
    payee_id: str
    period_from: date
    period_to: date
    settlement_date: date | None = None
    remarks: str | None = None


class SettlementOut(ORMModel):
    id: str
    settlement_no: str
    settlement_date: date
    period_from: date
    period_to: date
    payee_type: PayeeType
    payee_name: str | None = None
    trip_count: int
    total_km: int
    transportation_amount: Decimal
    loading_unloading_amount: Decimal
    point_incentive_amount: Decimal
    other_amount: Decimal
    gross_amount: Decimal
    advance_recovered: Decimal
    net_payable: Decimal
    status: SettlementStatus


def _payee_name(db: Session, payee_type: PayeeType, payee_id) -> str:
    if payee_type == PayeeType.VEHICLE_OWNER:
        owner = db.get(VehicleOwner, payee_id)
        return owner.name if owner else "—"
    driver = db.get(Driver, payee_id)
    return driver.name if driver else "—"


@router.get("/settlements/pending", response_model=list[PendingPayeeOut])
def pending_settlements(
    period_from: date = Query(...),
    period_to: date = Query(...),
    db: Session = Depends(get_db),
    _=ReadDep,
):
    """Who is owed what, for work that has not been settled yet.

    Grouped by payee because a settlement is a payment run for one party, not
    for one freight.
    """
    from app.models.freight import Freight  # local: avoids a circular import

    rows = (
        db.execute(
            select(FreightPayout)
            .join(Freight, FreightPayout.freight_id == Freight.id)
            .where(
                FreightPayout.settlement_id.is_(None),
                Freight.trip_date >= period_from,
                Freight.trip_date <= period_to,
            )
        )
        .scalars()
        .all()
    )

    buckets: dict[tuple[PayeeType, str], PendingPayeeOut] = {}
    freights: dict[tuple[PayeeType, str], set] = {}

    for row in rows:
        payee_id = (
            str(row.vehicle_owner_id)
            if row.payee_type == PayeeType.VEHICLE_OWNER and row.vehicle_owner_id
            else str(row.driver_id)
        )
        key = (row.payee_type, payee_id)

        bucket = buckets.get(key)
        if bucket is None:
            bucket = PendingPayeeOut(
                payee_type=row.payee_type,
                payee_id=payee_id,
                payee_name=_payee_name(db, row.payee_type, payee_id),
                freight_count=0,
                by_head={},
                gross=Decimal("0.00"),
                advance_outstanding=Decimal("0.00"),
                net_payable=Decimal("0.00"),
            )
            buckets[key] = bucket
            freights[key] = set()

        head = str(row.head)
        bucket.by_head[head] = money(bucket.by_head.get(head, Decimal("0")) + Decimal(row.amount))
        bucket.gross = money(bucket.gross + Decimal(row.amount))
        freights[key].add(row.freight_id)

    for key, bucket in buckets.items():
        bucket.freight_count = len(freights[key])

        advances = (
            db.execute(
                select(Advance).where(
                    Advance.payee_type == key[0],
                    (
                        Advance.vehicle_owner_id == key[1]
                        if key[0] == PayeeType.VEHICLE_OWNER
                        else Advance.driver_id == key[1]
                    ),
                    Advance.status.in_(
                        [AdvanceStatus.OUTSTANDING, AdvanceStatus.PART_RECOVERED]
                    ),
                )
            )
            .scalars()
            .all()
        )
        bucket.advance_outstanding = money(
            sum((a.outstanding for a in advances), Decimal("0"))
        )
        bucket.net_payable = money(bucket.gross - bucket.advance_outstanding)

    return sorted(buckets.values(), key=lambda b: -b.net_payable)


@router.post("/settlements", response_model=SettlementOut, status_code=201)
def create_settlement(payload: SettlementIn, db: Session = Depends(get_db), user: User = MoneyDep):
    """Close off a payee's unsettled work for a period."""
    from app.models.enums import ChargeHead
    from app.models.freight import Freight

    rows = (
        db.execute(
            select(FreightPayout)
            .join(Freight, FreightPayout.freight_id == Freight.id)
            .where(
                FreightPayout.settlement_id.is_(None),
                FreightPayout.payee_type == payload.payee_type,
                (
                    FreightPayout.vehicle_owner_id == payload.payee_id
                    if payload.payee_type == PayeeType.VEHICLE_OWNER
                    else FreightPayout.driver_id == payload.payee_id
                ),
                Freight.trip_date >= payload.period_from,
                Freight.trip_date <= payload.period_to,
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status_code=409, detail="Nothing outstanding for that payee and period")

    by_head: dict[str, Decimal] = {}
    for r in rows:
        by_head[str(r.head)] = by_head.get(str(r.head), Decimal("0")) + Decimal(r.amount)
    gross = money(sum(by_head.values(), Decimal("0")))

    advances = (
        db.execute(
            select(Advance).where(
                Advance.payee_type == payload.payee_type,
                (
                    Advance.vehicle_owner_id == payload.payee_id
                    if payload.payee_type == PayeeType.VEHICLE_OWNER
                    else Advance.driver_id == payload.payee_id
                ),
                Advance.status.in_([AdvanceStatus.OUTSTANDING, AdvanceStatus.PART_RECOVERED]),
            )
        )
        .scalars()
        .all()
    )

    recovered = Decimal("0")
    remaining = gross
    for advance in advances:
        if remaining <= 0:
            break
        take = min(advance.outstanding, remaining)
        advance.recovered_amount = money(Decimal(advance.recovered_amount) + take)
        advance.status = (
            AdvanceStatus.RECOVERED if advance.outstanding <= 0 else AdvanceStatus.PART_RECOVERED
        )
        recovered += take
        remaining -= take

    serial = (
        db.scalar(select(func.count()).select_from(Settlement)) or 0
    ) + 1

    settlement = Settlement(
        settlement_no=f"S/{payload.period_to.strftime('%Y%m')}/{serial:04d}",
        settlement_date=payload.settlement_date or date.today(),
        period_from=payload.period_from,
        period_to=payload.period_to,
        payee_type=payload.payee_type,
        driver_id=payload.payee_id if payload.payee_type == PayeeType.DRIVER else None,
        vehicle_owner_id=(
            payload.payee_id if payload.payee_type == PayeeType.VEHICLE_OWNER else None
        ),
        trip_count=len({r.freight_id for r in rows}),
        total_km=0,
        transportation_amount=by_head.get(str(ChargeHead.TRANSPORTATION), Decimal("0")),
        loading_unloading_amount=by_head.get(str(ChargeHead.LOADING_UNLOADING), Decimal("0")),
        point_incentive_amount=by_head.get(str(ChargeHead.POINT_INCENTIVE), Decimal("0")),
        other_amount=Decimal("0"),
        gross_amount=gross,
        advance_recovered=money(recovered),
        deductions=Decimal("0"),
        net_payable=money(gross - recovered),
        status=SettlementStatus.DRAFT,
        remarks=payload.remarks,
        prepared_by_id=user.id,
    )
    db.add(settlement)
    db.flush()

    for r in rows:
        r.settlement_id = settlement.id

    db.commit()
    db.refresh(settlement)
    return _settlement_out(db, settlement)


def _settlement_out(db: Session, s: Settlement) -> SettlementOut:
    out = SettlementOut.model_validate(s)
    out.payee_name = _payee_name(
        db, s.payee_type, s.vehicle_owner_id if s.vehicle_owner_id else s.driver_id
    )
    return out


@router.get("/settlements", response_model=list[SettlementOut])
def list_settlements(db: Session = Depends(get_db), _=ReadDep):
    rows = (
        db.execute(select(Settlement).order_by(Settlement.settlement_date.desc()))
        .scalars()
        .all()
    )
    return [_settlement_out(db, s) for s in rows]


class SettlementStatusIn(BaseModel):
    status: SettlementStatus
    payment_reference: str | None = Field(default=None, max_length=64)


@router.patch("/settlements/{settlement_id}", response_model=SettlementOut)
def set_settlement_status(
    settlement_id: str,
    payload: SettlementStatusIn,
    db: Session = Depends(get_db),
    _=MoneyDep,
):
    settlement = db.get(Settlement, settlement_id)
    if settlement is None:
        raise HTTPException(status_code=404, detail="Settlement not found")
    settlement.status = payload.status
    if payload.payment_reference:
        settlement.payment_reference = payload.payment_reference
    db.commit()
    db.refresh(settlement)
    return _settlement_out(db, settlement)
