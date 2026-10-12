"""Cartons that came back.

The box reconciliation has always counted returns — loaded minus delivered
minus returned is the figure that says whether anything is missing. What was
missing was any way to RECORD one, so every carton that came back showed up as
"unaccounted", which is the alarm that should be reserved for a box nobody can
find.

A return is four facts: which carton, what happened to it, why, and who said
so. The reason is the one that earns its place. "12 boxes came back" is a
number nobody can act on; "4 refused by Anand Agencies, wrong model" is
something the vendor can be told and the warehouse can put right.

Recorded against individual cartons rather than a count, because that is how
they come back — three of a bill's six, not all or nothing — and because the
vendor's first question is always which ones.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import WAREHOUSE_ROLES, require_roles
from app.db.session import get_db
from app.models.consignment import Box, Consignment
from app.models.enums import BoxStatus
from app.models.freight import FreightPoint
from app.models.user import User

router = APIRouter(prefix="/api", tags=["returns"])

OpsDep = Depends(require_roles(*WAREHOUSE_ROLES))

# What a carton coming back can be. Anything else is not a return: a box still
# on the vehicle is IN_TRANSIT, and one handed over is DELIVERED.
RETURNABLE = {
    BoxStatus.RETURNED_TO_WAREHOUSE,
    BoxStatus.DAMAGED,
    BoxStatus.NOT_DELIVERED,
}


class ReturnIn(BaseModel):
    # Barcodes rather than ids: the person doing this has the cartons in front
    # of them with stickers on, and a scanner or a keyboard. Asking them to
    # look up database ids would make the screen unusable at the godown door.
    barcodes: list[str] = Field(min_length=1, max_length=500)
    status: BoxStatus = BoxStatus.RETURNED_TO_WAREHOUSE
    reason: str = Field(min_length=3, max_length=500)


class ReturnedBoxOut(BaseModel):
    box_id: str
    barcode: str
    item_no: int
    item_name: str | None
    status: BoxStatus
    reason: str | None
    returned_at: datetime | None
    returned_by: str | None
    vendor_bill_no: str
    consignee_name: str | None
    trip_no: str | None
    trip_date: date | None


class ReturnResult(BaseModel):
    recorded: list[ReturnedBoxOut]
    # Barcodes that are not ours, or were already recorded. Reported rather
    # than failed on, because a stack of cartons at the door should not be
    # rejected wholesale because one sticker was misread.
    unknown: list[str]
    already: list[str]


def _out(box: Box) -> ReturnedBoxOut:
    consignment = box.consignment
    point = consignment.freight_point if consignment else None
    freight = point.freight if point else None
    return ReturnedBoxOut(
        box_id=str(box.id),
        barcode=box.barcode,
        item_no=box.item_no,
        item_name=box.item_name,
        status=box.status,
        reason=box.return_reason,
        returned_at=box.returned_at,
        returned_by=box.returned_by.full_name if box.returned_by else None,
        vendor_bill_no=consignment.vendor_bill_no if consignment else "",
        consignee_name=(
            point.consignee.name
            if point and point.consignee
            else (consignment.consignee.name if consignment and consignment.consignee else None)
        ),
        trip_no=freight.trip_no if freight else None,
        trip_date=freight.trip_date if freight else None,
    )


@router.post("/returns", response_model=ReturnResult, status_code=201)
def record_returns(payload: ReturnIn, db: Session = Depends(get_db), user: User = OpsDep):
    """Record cartons that came back, by their stickers."""
    if payload.status not in RETURNABLE:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{payload.status} is not a return. A carton that came back is "
                "returned to the warehouse, damaged, or not delivered."
            ),
        )

    wanted = [code.strip().upper() for code in payload.barcodes if code.strip()]
    if not wanted:
        raise HTTPException(status_code=422, detail="No barcodes given")

    found = {
        box.barcode.upper(): box
        for box in db.execute(
            select(Box)
            .options(joinedload(Box.consignment).joinedload(Consignment.freight_point))
            .where(Box.barcode.in_(wanted))
        )
        .unique()
        .scalars()
    }

    recorded: list[Box] = []
    unknown: list[str] = []
    already: list[str] = []
    now = datetime.now()

    for code in wanted:
        box = found.get(code)
        if box is None:
            unknown.append(code)
            continue
        # Recording the same carton twice would move its reason and its
        # timestamp, quietly rewriting who said what and when.
        if box.returned_at is not None:
            already.append(code)
            continue

        box.status = payload.status
        box.return_reason = payload.reason.strip()
        box.returned_at = now
        box.returned_by_id = user.id
        recorded.append(box)

    db.commit()
    for box in recorded:
        db.refresh(box)

    return ReturnResult(
        recorded=[_out(b) for b in recorded],
        unknown=unknown,
        already=already,
    )


@router.get("/returns", response_model=list[ReturnedBoxOut])
def list_returns(
    period_from: date | None = None,
    period_to: date | None = None,
    status: BoxStatus | None = None,
    db: Session = Depends(get_db),
    _=OpsDep,
):
    """Everything that has come back, newest first."""
    stmt = (
        select(Box)
        .options(joinedload(Box.consignment).joinedload(Consignment.freight_point))
        .where(Box.returned_at.isnot(None))
        # id breaks the tie, or cartons recorded in the same action swap places
        # between one refresh and the next.
        .order_by(Box.returned_at.desc(), Box.id)
    )
    if status:
        stmt = stmt.where(Box.status == status)
    if period_from:
        stmt = stmt.where(Box.returned_at >= datetime.combine(period_from, datetime.min.time()))
    if period_to:
        stmt = stmt.where(Box.returned_at <= datetime.combine(period_to, datetime.max.time()))

    return [_out(b) for b in db.execute(stmt).unique().scalars()]


class ReturnSummaryOut(BaseModel):
    returned_to_warehouse: int
    damaged: int
    not_delivered: int
    total: int
    # The bills worst affected, so a pattern with one customer or one article
    # is visible rather than buried in a list of cartons.
    by_customer: list[dict]


@router.get("/returns/summary", response_model=ReturnSummaryOut)
def returns_summary(
    period_from: date | None = None,
    period_to: date | None = None,
    db: Session = Depends(get_db),
    _=OpsDep,
):
    rows = list_returns(period_from=period_from, period_to=period_to, db=db)

    counts: dict[str, int] = {}
    for row in rows:
        name = row.consignee_name or "Unknown"
        counts[name] = counts.get(name, 0) + 1

    return ReturnSummaryOut(
        returned_to_warehouse=sum(
            1 for r in rows if r.status == BoxStatus.RETURNED_TO_WAREHOUSE
        ),
        damaged=sum(1 for r in rows if r.status == BoxStatus.DAMAGED),
        not_delivered=sum(1 for r in rows if r.status == BoxStatus.NOT_DELIVERED),
        total=len(rows),
        by_customer=[
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        ],
    )
