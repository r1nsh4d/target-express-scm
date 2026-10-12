"""What to do next, worked out from what is actually there.

The people using this have no software background. The commonest failure is not
that a screen is confusing on its own — it is that nothing anywhere says which
screen to be on. A bill is entered and sits unassigned; a freight is built and
never dispatched; a trip finishes and is never invoiced. Each is invisible
until somebody happens to look at the right list.

So the application works it out and says so. Every suggestion is derived from a
real count, carries the number, and links to the screen that resolves it —
never a generic "get started" tile, which is the kind of advice that teaches
people to ignore advice.

Ordered by cost of leaving it. A trip finished three weeks ago and never billed
is money not asked for; a draft freight is an afternoon's inconvenience. The
first thing on the list should be the first thing worth doing.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import BACK_OFFICE_ROLES, require_roles
from app.db.session import get_db
from app.models.billing import VendorInvoice, VendorInvoiceLine
from app.models.consignment import Consignment
from app.models.enquiry import Enquiry
from app.models.enums import (
    EnquiryStatus,
    FreightStatus,
    InvoiceStatus,
)
from app.models.freight import Freight, FreightLeg, FreightPoint

router = APIRouter(prefix="/api", tags=["next steps"])

ReadDep = Depends(require_roles(*BACK_OFFICE_ROLES))


class NextStep(BaseModel):
    key: str
    # Written as an instruction, not a label. "Put 4 bills on a freight", not
    # "Unassigned bills: 4" — the second is a fact and leaves the reader to
    # work out what it is asking of them.
    title: str
    detail: str
    count: int
    to: str
    # 'now' is money or a vehicle waiting; 'soon' is housekeeping.
    urgency: str


class NextStepsOut(BaseModel):
    steps: list[NextStep]
    # Nothing outstanding. Worth saying explicitly: a blank space reads as a
    # screen that has not loaded.
    all_clear: bool


@router.get("/next-steps", response_model=NextStepsOut)
def next_steps(db: Session = Depends(get_db), _=ReadDep) -> NextStepsOut:
    steps: list[NextStep] = []
    today = date.today()

    def count(stmt) -> int:
        return int(db.scalar(stmt) or 0)

    # --- money already earned and not asked for ----------------------------- #
    billed = select(VendorInvoiceLine.freight_id)
    unbilled = count(
        select(func.count())
        .select_from(Freight)
        .where(
            Freight.status == FreightStatus.COMPLETED,
            Freight.id.notin_(billed),
        )
    )
    if unbilled:
        oldest = db.scalar(
            select(func.min(Freight.trip_date)).where(
                Freight.status == FreightStatus.COMPLETED,
                Freight.id.notin_(billed),
            )
        )
        age = (today - oldest).days if oldest else 0
        steps.append(
            NextStep(
                key="unbilled",
                title=f"Bill {unbilled} finished trip{'s' if unbilled > 1 else ''}",
                detail=(
                    f"The oldest finished {age} days ago and has not been invoiced."
                    if age > 2
                    else "These are done and ready to invoice."
                ),
                count=unbilled,
                to="/invoices",
                urgency="now" if age > 7 else "soon",
            )
        )

    # --- invoices issued and not paid ---------------------------------------- #
    unpaid = count(
        select(func.count())
        .select_from(VendorInvoice)
        .where(VendorInvoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.SENT]))
    )
    if unpaid:
        oldest_inv = db.scalar(
            select(func.min(VendorInvoice.invoice_date)).where(
                VendorInvoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.SENT])
            )
        )
        days = (today - oldest_inv).days if oldest_inv else 0
        steps.append(
            NextStep(
                key="unpaid",
                title=f"Chase {unpaid} unpaid invoice{'s' if unpaid > 1 else ''}",
                detail=(
                    f"The oldest has been waiting {days} days."
                    if days > 20
                    else "Record the payment here when it arrives."
                ),
                count=unpaid,
                to="/money-in",
                urgency="now" if days > 30 else "soon",
            )
        )

    # --- a vehicle that could be moving -------------------------------------- #
    ready = count(
        select(func.count())
        .select_from(Freight)
        .where(
            Freight.status.in_([FreightStatus.PLANNED, FreightStatus.LOADING]),
            Freight.id.in_(select(FreightLeg.freight_id)),
            Freight.trip_date <= today,
        )
    )
    if ready:
        steps.append(
            NextStep(
                key="dispatch",
                title=f"Dispatch {ready} loaded trip{'s' if ready > 1 else ''}",
                detail="A vehicle and driver are assigned. Dispatching issues the LR number and opens the customers' tracking links.",
                count=ready,
                to="/freights",
                urgency="now",
            )
        )

    # --- a stop with nothing on it -------------------------------------------- #
    with_bills = select(Consignment.freight_point_id).where(
        Consignment.freight_point_id.isnot(None)
    )
    empty_stops = count(
        select(func.count())
        .select_from(FreightPoint)
        .join(Freight, FreightPoint.freight_id == Freight.id)
        .where(
            Freight.status.in_(
                [FreightStatus.DRAFT, FreightStatus.PLANNED, FreightStatus.LOADING]
            ),
            FreightPoint.id.notin_(with_bills),
        )
    )
    if empty_stops:
        steps.append(
            NextStep(
                key="empty_stops",
                title=f"Put bills on {empty_stops} empty stop{'s' if empty_stops > 1 else ''}",
                detail="These stops have no bills, so there is nothing to label and nothing to deliver there.",
                count=empty_stops,
                to="/freights",
                urgency="now",
            )
        )

    # --- bills waiting for a lorry --------------------------------------------- #
    waiting = count(
        select(func.count())
        .select_from(Consignment)
        .where(Consignment.freight_point_id.is_(None))
    )
    if waiting:
        steps.append(
            NextStep(
                key="unassigned",
                title=f"Put {waiting} bill{'s' if waiting > 1 else ''} on a freight",
                detail="Entered but not on any trip yet. Until they are, they cannot be labelled or delivered.",
                count=waiting,
                to="/day-sheet",
                urgency="soon",
            )
        )

    # --- a trip out that never came back ----------------------------------------- #
    stale = count(
        select(func.count())
        .select_from(Freight)
        .where(
            Freight.status.in_([FreightStatus.DISPATCHED, FreightStatus.IN_TRANSIT]),
            Freight.trip_date < today - timedelta(days=2),
        )
    )
    if stale:
        steps.append(
            NextStep(
                key="stale",
                title=f"Close {stale} trip{'s' if stale > 1 else ''} still showing as out",
                detail="Out for more than two days. If the vehicle is back, the closing odometer was never entered — and the trip cannot be billed until it is.",
                count=stale,
                to="/freights",
                urgency="now",
            )
        )

    # --- somebody asked to work with us -------------------------------------------- #
    enquiries = count(
        select(func.count())
        .select_from(Enquiry)
        .where(Enquiry.status == EnquiryStatus.NEW, Enquiry.is_spam.is_(False))
    )
    if enquiries:
        steps.append(
            NextStep(
                key="enquiries",
                title=f"Call {enquiries} new enquir{'ies' if enquiries > 1 else 'y'}",
                detail="The website promises a call within one working day.",
                count=enquiries,
                to="/enquiries",
                urgency="now",
            )
        )

    order = {"now": 0, "soon": 1}
    steps.sort(key=lambda s: (order.get(s.urgency, 2), -s.count))

    return NextStepsOut(steps=steps, all_clear=not steps)
