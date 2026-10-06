"""Money out of the business (vendor invoices) and money out to people
(driver and vehicle-owner settlements)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import ACCOUNTS_ROLES, BACK_OFFICE_ROLES, require_roles
from app.db.session import get_db
from app.models.billing import VendorInvoice
from app.models.enums import AdvanceStatus, InvoiceStatus, PayeeType, SettlementStatus
from app.models.fleet import Driver, VehicleOwner
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


class PreviewLine(BaseModel):
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    db.commit()
    db.refresh(invoice)
    return _invoice_out(invoice, with_lines=True)


def _invoice_out(inv: VendorInvoice, with_lines: bool = False) -> InvoiceOut:
    out = InvoiceOut.model_validate(inv)
    out.vendor_division_name = inv.vendor_division.name if inv.vendor_division else None
    out.line_count = len(inv.lines)
    out.lines = [InvoiceLineOut.model_validate(line) for line in inv.lines] if with_lines else []
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


@router.patch("/invoices/{invoice_id}", response_model=InvoiceRowOut)
def set_invoice_status(
    invoice_id: str, payload: InvoiceStatusIn, db: Session = Depends(get_db), _=MoneyDep
):
    invoice = db.get(VendorInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = payload.status
    db.commit()
    db.refresh(invoice)
    return _invoice_out(invoice)


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
