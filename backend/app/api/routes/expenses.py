"""On-road spending, and the queue that approves it.

Everything a driver pays or draws lands here. Approval is a separate act from
entry: the driver records what happened, the office decides what is settled.
"""

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import ACCOUNTS_ROLES, BACK_OFFICE_ROLES, WAREHOUSE_ROLES, require_roles
from app.db.session import get_db
from app.models.enums import ApprovalStatus, EntryMode, ExpenseType, PaidBy
from app.models.expense import TripExpense
from app.models.fleet import Labour
from app.models.freight import Freight
from app.models.user import User

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

ReadDep = Depends(require_roles(*BACK_OFFICE_ROLES))
ApproveDep = Depends(require_roles(*ACCOUNTS_ROLES))
OpsDep = Depends(require_roles(*WAREHOUSE_ROLES))


class ExpenseOut(BaseModel):
    id: str
    freight_id: str
    trip_no: str | None = None
    trip_date: date | None = None
    driver_name: str | None = None
    type: ExpenseType
    amount: Decimal
    paid_by: PaidBy
    billable_to_vendor: bool
    receipt_photo_url: str | None
    labour_id: str | None
    labour_count: int | None
    entry_mode: EntryMode
    approval_status: ApprovalStatus
    rejection_reason: str | None
    remarks: str | None
    created_at: datetime


class DecisionIn(BaseModel):
    approve: bool
    reason: str | None = Field(default=None, max_length=300)


class LoadingExpenseIn(BaseModel):
    """Payment to the godown crew who loaded the vehicle."""

    freight_id: str
    amount: Decimal = Field(gt=0)
    labour_id: str | None = None
    labour_count: int | None = Field(default=None, ge=1, le=20)
    receipt_photo_url: str | None = None
    remarks: str | None = None


def _out(e: TripExpense) -> ExpenseOut:
    freight = e.freight
    leg = freight.legs[0] if freight and freight.legs else None
    return ExpenseOut(
        id=str(e.id),
        freight_id=str(e.freight_id),
        trip_no=freight.trip_no if freight else None,
        trip_date=freight.trip_date if freight else None,
        driver_name=leg.driver.name if leg and leg.driver else None,
        type=e.type,
        amount=e.amount,
        paid_by=e.paid_by,
        billable_to_vendor=e.billable_to_vendor,
        receipt_photo_url=e.receipt_photo_url,
        labour_id=str(e.labour_id) if e.labour_id else None,
        labour_count=e.labour_count,
        entry_mode=e.entry_mode,
        approval_status=e.approval_status,
        rejection_reason=e.rejection_reason,
        remarks=e.remarks,
        created_at=e.created_at,
    )


@router.get("", response_model=list[ExpenseOut])
def list_expenses(
    approval_status: ApprovalStatus | None = Query(default=None),
    freight_id: str | None = None,
    limit: int = Query(default=200, le=500),
    db: Session = Depends(get_db),
    _=ReadDep,
):
    stmt = (
        select(TripExpense)
        .options(joinedload(TripExpense.freight))
        .order_by(TripExpense.created_at.desc())
        .limit(limit)
    )
    if approval_status:
        stmt = stmt.where(TripExpense.approval_status == approval_status)
    if freight_id:
        stmt = stmt.where(TripExpense.freight_id == freight_id)

    return [_out(e) for e in db.execute(stmt).unique().scalars().all()]


@router.post("/loading", response_model=ExpenseOut, status_code=201)
def record_loading_charge(
    payload: LoadingExpenseIn, db: Session = Depends(get_db), user: User = OpsDep
):
    """What the godown crew was paid to load this freight.

    Recorded against a named helper where there is one, so a month's payments to
    one person can be totalled without reading every freight.
    """
    if db.get(Freight, payload.freight_id) is None:
        raise HTTPException(status_code=404, detail="Freight not found")
    if payload.labour_id and db.get(Labour, payload.labour_id) is None:
        raise HTTPException(status_code=404, detail="Labour not found")

    expense = TripExpense(
        freight_id=payload.freight_id,
        type=ExpenseType.LOADING,
        amount=payload.amount,
        paid_by=PaidBy.COMPANY,
        # Loading at the godown is our own cost, not something the vendor is
        # separately billed for.
        billable_to_vendor=False,
        labour_id=payload.labour_id,
        labour_count=payload.labour_count,
        receipt_photo_url=payload.receipt_photo_url,
        entered_by_id=user.id,
        entry_mode=EntryMode.ADMIN_ON_BEHALF,
        remarks=payload.remarks,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return _out(expense)


@router.patch("/{expense_id}", response_model=ExpenseOut)
def decide(
    expense_id: str, payload: DecisionIn, db: Session = Depends(get_db), user: User = ApproveDep
):
    """Approve or reject. A rejection has to say why — the driver sees it."""
    expense = db.get(TripExpense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")

    if not payload.approve and not payload.reason:
        raise HTTPException(
            status_code=400,
            detail="Give a reason for rejecting it — the driver is shown this.",
        )

    expense.approval_status = (
        ApprovalStatus.APPROVED if payload.approve else ApprovalStatus.REJECTED
    )
    expense.rejection_reason = None if payload.approve else payload.reason
    expense.approved_by_id = user.id
    expense.approved_at = datetime.now()

    db.commit()
    db.refresh(expense)
    return _out(expense)
