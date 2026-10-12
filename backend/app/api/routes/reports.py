"""What the business actually did, over a period.

The dashboard answers "what is happening today". This answers the questions
asked at the end of a month: did we make anything, where did it come from, who
is slow to pay, and what came back.

Every figure is built from the documents rather than from a separate ledger, so
a report can never disagree with the invoice or the settlement it summarises.
That costs some query time once a month and removes a whole category of "the
report says one thing and the invoice says another".

Two deliberate choices about what money means here:

  * Revenue is INVOICED, not received. An invoice raised is work done and owed
    for; whether the vendor has paid yet is a separate question and has its own
    figure. Mixing them produces a month that looks terrible because a large
    customer pays on the 5th.
  * Cost is what was PAID OUT for the same freights — driver and owner payouts,
    plus approved expenses. Not what was budgeted, and not a share of overhead,
    because neither is a number anybody here can check against a bank
    statement.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import BACK_OFFICE_ROLES, require_roles
from app.db.session import get_db
from app.models.billing import VendorInvoice, VendorInvoiceLine
from app.models.consignment import Box, Consignment
from app.models.enums import (
    ApprovalStatus,
    BoxStatus,
    FreightStatus,
    InvoiceStatus,
)
from app.models.expense import TripExpense
from app.models.freight import Freight, FreightPoint
from app.models.settlement import FreightPayout
from app.services.rating import money

router = APIRouter(prefix="/api/reports", tags=["reports"])

ReadDep = Depends(require_roles(*BACK_OFFICE_ROLES))


class MoneyBlock(BaseModel):
    invoiced: Decimal
    received: Decimal
    outstanding: Decimal
    # What went out against the same work.
    paid_to_drivers_and_owners: Decimal
    expenses: Decimal
    margin: Decimal
    margin_percent: Decimal


class WorkBlock(BaseModel):
    trips: int
    points: int
    km: int
    boxes_delivered: int
    boxes_returned: int
    # Returns as a share of what was carried. The number anybody judges a
    # logistics operation by, and it is meaningless without the denominator.
    return_rate_percent: Decimal


class MonthRow(BaseModel):
    month: str
    trips: int
    invoiced: Decimal
    margin: Decimal


class NamedAmount(BaseModel):
    name: str
    trips: int
    amount: Decimal


class DriverRow(BaseModel):
    name: str
    trips: int
    km: int
    earned: Decimal


class OverdueRow(BaseModel):
    invoice_no: str
    vendor_division_name: str | None
    invoice_date: date
    total: Decimal
    days_outstanding: int


class ReportOut(BaseModel):
    period_from: date
    period_to: date
    money: MoneyBlock
    work: WorkBlock
    by_month: list[MonthRow]
    by_division: list[NamedAmount]
    top_customers: list[NamedAmount]
    drivers: list[DriverRow]
    overdue: list[OverdueRow]


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    if not whole:
        return Decimal("0.00")
    return money(part * Decimal("100") / whole)


@router.get("", response_model=ReportOut)
def overview(
    period_from: date | None = Query(default=None),
    period_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _=ReadDep,
) -> ReportOut:
    today = date.today()
    return build_overview(
        db,
        period_from or (today - timedelta(days=90)),
        period_to or today,
    )


def build_overview(db: Session, start: date, end: date) -> ReportOut:
    """The report itself, as a plain function.

    Kept separate from the endpoint because the endpoint's defaults are FastAPI
    Query objects, not dates — calling it as an ordinary function hands those
    straight to the database and fails somewhere far from the cause. Anything
    inside the application calls this instead.
    """
    today = date.today()

    # --- money in ---------------------------------------------------------- #
    invoices = list(
        db.execute(
            select(VendorInvoice)
            .options(joinedload(VendorInvoice.vendor_division))
            .where(
                VendorInvoice.invoice_date >= start,
                VendorInvoice.invoice_date <= end,
                VendorInvoice.status != InvoiceStatus.CANCELLED,
            )
        )
        .unique()
        .scalars()
    )
    invoiced = money(sum((Decimal(i.total or 0) for i in invoices), Decimal("0")))
    received = money(
        sum(
            (Decimal(i.amount_received or 0) for i in invoices if i.status == InvoiceStatus.PAID),
            Decimal("0"),
        )
    )

    # --- the work it was for ----------------------------------------------- #
    freights = list(
        db.execute(
            select(Freight).where(
                Freight.trip_date >= start,
                Freight.trip_date <= end,
                Freight.status != FreightStatus.CANCELLED,
            )
        )
        .unique()
        .scalars()
    )
    freight_ids = [f.id for f in freights]

    trips = len(freights)
    km = sum(int(f.total_km or 0) for f in freights)

    points = 0
    if freight_ids:
        points = int(
            db.scalar(
                select(func.count())
                .select_from(FreightPoint)
                .where(FreightPoint.freight_id.in_(freight_ids))
            )
            or 0
        )

    # --- money out --------------------------------------------------------- #
    paid_out = Decimal("0")
    expenses = Decimal("0")
    if freight_ids:
        paid_out = money(
            db.scalar(
                select(func.coalesce(func.sum(FreightPayout.amount), 0)).where(
                    FreightPayout.freight_id.in_(freight_ids)
                )
            )
            or 0
        )
        expenses = money(
            db.scalar(
                select(func.coalesce(func.sum(TripExpense.amount), 0)).where(
                    TripExpense.freight_id.in_(freight_ids),
                    TripExpense.approval_status == ApprovalStatus.APPROVED,
                )
            )
            or 0
        )

    margin = money(invoiced - paid_out - expenses)

    # --- cartons ----------------------------------------------------------- #
    delivered = returned = 0
    if freight_ids:
        box_rows = list(
            db.execute(
                select(Box.status, func.count())
                .select_from(Box)
                .join(Consignment, Box.consignment_id == Consignment.id)
                .join(FreightPoint, Consignment.freight_point_id == FreightPoint.id)
                .where(FreightPoint.freight_id.in_(freight_ids))
                .group_by(Box.status)
            )
        )
        counts = {status: count for status, count in box_rows}
        delivered = counts.get(BoxStatus.DELIVERED, 0)
        returned = (
            counts.get(BoxStatus.RETURNED_TO_WAREHOUSE, 0)
            + counts.get(BoxStatus.DAMAGED, 0)
            + counts.get(BoxStatus.NOT_DELIVERED, 0)
        )

    # --- month by month ----------------------------------------------------- #
    per_month_trips: dict[str, int] = defaultdict(int)
    for f in freights:
        per_month_trips[f.trip_date.strftime("%Y-%m")] += 1

    per_month_invoiced: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for i in invoices:
        per_month_invoiced[i.invoice_date.strftime("%Y-%m")] += Decimal(i.total or 0)

    per_month_out: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    if freight_ids:
        by_freight = {f.id: f.trip_date.strftime("%Y-%m") for f in freights}
        for freight_id, amount in db.execute(
            select(FreightPayout.freight_id, func.coalesce(func.sum(FreightPayout.amount), 0))
            .where(FreightPayout.freight_id.in_(freight_ids))
            .group_by(FreightPayout.freight_id)
        ):
            per_month_out[by_freight.get(freight_id, "")] += Decimal(amount or 0)

    by_month = [
        MonthRow(
            month=m,
            trips=per_month_trips.get(m, 0),
            invoiced=money(per_month_invoiced.get(m, Decimal("0"))),
            margin=money(per_month_invoiced.get(m, Decimal("0")) - per_month_out.get(m, Decimal("0"))),
        )
        for m in sorted(set(per_month_trips) | set(per_month_invoiced))
    ]

    # --- who it came from --------------------------------------------------- #
    division_totals: dict[str, tuple[int, Decimal]] = {}
    for i in invoices:
        name = i.vendor_division.name if i.vendor_division else "Unknown"
        count, amount = division_totals.get(name, (0, Decimal("0")))
        division_totals[name] = (count + len(i.lines), amount + Decimal(i.total or 0))

    by_division = [
        NamedAmount(name=name, trips=count, amount=money(amount))
        for name, (count, amount) in sorted(
            division_totals.items(), key=lambda kv: -kv[1][1]
        )
    ]

    # --- busiest customers --------------------------------------------------- #
    customer_counts: dict[str, int] = defaultdict(int)
    if freight_ids:
        for name, count in db.execute(
            select(FreightPoint.consignee_id, func.count())
            .where(FreightPoint.freight_id.in_(freight_ids))
            .group_by(FreightPoint.consignee_id)
        ):
            customer_counts[str(name)] += count

    from app.models.consignee import Consignee  # local: only needed here

    top_customers: list[NamedAmount] = []
    if customer_counts:
        names = {
            str(c.id): c.name
            for c in db.execute(
                select(Consignee).where(Consignee.id.in_(list(customer_counts)))
            ).scalars()
        }
        top_customers = [
            NamedAmount(name=names.get(cid, "Unknown"), trips=count, amount=Decimal("0"))
            for cid, count in sorted(customer_counts.items(), key=lambda kv: -kv[1])[:10]
        ]

    # --- drivers ------------------------------------------------------------- #
    drivers: list[DriverRow] = []
    if freight_ids:
        from app.models.fleet import Driver
        from app.models.freight import FreightLeg

        legs = list(
            db.execute(
                select(FreightLeg).where(FreightLeg.freight_id.in_(freight_ids))
            ).scalars()
        )
        per_driver: dict[str, dict] = {}
        for leg in legs:
            row = per_driver.setdefault(
                str(leg.driver_id), {"trips": 0, "km": 0, "earned": Decimal("0")}
            )
            row["trips"] += 1
            row["km"] += int(leg.leg_distance_km or 0)

        for payout in db.execute(
            select(FreightPayout).where(FreightPayout.freight_id.in_(freight_ids))
        ).scalars():
            if payout.driver_id is None:
                continue
            key = str(payout.driver_id)
            if key in per_driver:
                per_driver[key]["earned"] += Decimal(payout.amount or 0)

        if per_driver:
            names = {
                str(d.id): d.name
                for d in db.execute(
                    select(Driver).where(Driver.id.in_(list(per_driver)))
                ).scalars()
            }
            drivers = [
                DriverRow(
                    name=names.get(did, "Unknown"),
                    trips=row["trips"],
                    km=row["km"],
                    earned=money(row["earned"]),
                )
                for did, row in sorted(per_driver.items(), key=lambda kv: -kv[1]["km"])
                if did in names
            ]

    # --- who has not paid ----------------------------------------------------- #
    overdue = [
        OverdueRow(
            invoice_no=i.invoice_no,
            vendor_division_name=i.vendor_division.name if i.vendor_division else None,
            invoice_date=i.invoice_date,
            total=money(Decimal(i.total or 0)),
            days_outstanding=(today - i.invoice_date).days,
        )
        for i in invoices
        if i.status in (InvoiceStatus.ISSUED, InvoiceStatus.SENT)
    ]
    overdue.sort(key=lambda r: -r.days_outstanding)

    carried = delivered + returned
    return ReportOut(
        period_from=start,
        period_to=end,
        money=MoneyBlock(
            invoiced=invoiced,
            received=received,
            outstanding=money(invoiced - received),
            paid_to_drivers_and_owners=paid_out,
            expenses=expenses,
            margin=margin,
            margin_percent=_pct(margin, invoiced),
        ),
        work=WorkBlock(
            trips=trips,
            points=points,
            km=km,
            boxes_delivered=delivered,
            boxes_returned=returned,
            return_rate_percent=_pct(Decimal(returned), Decimal(carried)),
        ),
        by_month=by_month,
        by_division=by_division,
        top_customers=top_customers,
        drivers=drivers[:10],
        overdue=overdue[:10],
    )


class EarningsOut(BaseModel):
    """The money block alone, for the dashboard."""

    month_invoiced: Decimal
    month_received: Decimal
    month_margin: Decimal
    outstanding_total: Decimal
    outstanding_count: int
    oldest_unpaid_days: int | None


@router.get("/earnings", response_model=EarningsOut)
def earnings(db: Session = Depends(get_db), _=ReadDep) -> EarningsOut:
    """This month's money, and what is still owed from any month.

    Outstanding deliberately ignores the month boundary: an invoice from August
    that nobody has paid is the most important number on the screen, and it
    would vanish from a strictly month-to-date figure.
    """
    today = date.today()
    month_start = today.replace(day=1)

    report = build_overview(db, month_start, today)

    unpaid = list(
        db.execute(
            select(VendorInvoice).where(
                VendorInvoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.SENT])
            )
        ).scalars()
    )
    oldest = min((i.invoice_date for i in unpaid), default=None)

    return EarningsOut(
        month_invoiced=report.money.invoiced,
        month_received=report.money.received,
        month_margin=report.money.margin,
        outstanding_total=money(
            sum((Decimal(i.total or 0) for i in unpaid), Decimal("0"))
        ),
        outstanding_count=len(unpaid),
        oldest_unpaid_days=(today - oldest).days if oldest else None,
    )
