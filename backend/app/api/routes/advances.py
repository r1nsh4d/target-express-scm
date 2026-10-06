from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ACCOUNTS_ROLES, BACK_OFFICE_ROLES, WAREHOUSE_ROLES, require_roles
from app.db.session import get_db
from app.models.enums import AdvanceStatus, PayeeType
from app.models.freight import Freight
from app.models.settlement import Advance
from app.models.user import User
from app.services.settlement import head_totals, trip_accounts

router = APIRouter(prefix="/api", tags=["advances"])


class AdvanceIn(BaseModel):
    """An advance drawn against a trip.

    On a rented vehicle this is what the owner takes when the vehicle leaves;
    it is recovered against the trip's payouts when the vehicle returns.
    """

    payee_type: PayeeType
    driver_id: str | None = None
    vehicle_owner_id: str | None = None
    freight_id: str | None = None
    advance_date: date
    amount: Decimal = Field(gt=0)
    mode: str | None = None
    reference: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def check_payee(self) -> "AdvanceIn":
        if self.payee_type == PayeeType.VEHICLE_OWNER and not self.vehicle_owner_id:
            raise ValueError("vehicle_owner_id is required for a vehicle owner advance")
        if self.payee_type == PayeeType.DRIVER and not self.driver_id:
            raise ValueError("driver_id is required for a driver advance")
        return self


class AdvanceOut(BaseModel):
    id: str
    payee_type: PayeeType
    driver_id: str | None
    vehicle_owner_id: str | None
    freight_id: str | None
    advance_date: date
    amount: Decimal
    recovered_amount: Decimal
    outstanding: Decimal
    status: AdvanceStatus
    mode: str | None
    reference: str | None


class TripAccountOut(BaseModel):
    payee_type: PayeeType
    payee_id: str | None
    payee_name: str | None
    # The driver is named even when the money goes to the vehicle owner.
    driver_names: list[str]
    by_head: dict[str, Decimal]
    gross: Decimal
    advance_drawn: Decimal
    advance_recovered: Decimal
    balance_payable: Decimal
    advance_carried_forward: Decimal
    is_closed: bool


def _to_out(advance: Advance) -> AdvanceOut:
    return AdvanceOut(
        id=str(advance.id),
        payee_type=advance.payee_type,
        driver_id=str(advance.driver_id) if advance.driver_id else None,
        vehicle_owner_id=str(advance.vehicle_owner_id) if advance.vehicle_owner_id else None,
        freight_id=str(advance.freight_id) if advance.freight_id else None,
        advance_date=advance.advance_date,
        amount=advance.amount,
        recovered_amount=advance.recovered_amount,
        outstanding=advance.outstanding,
        status=advance.status,
        mode=advance.mode,
        reference=advance.reference,
    )


@router.post("/advances", response_model=AdvanceOut, status_code=status.HTTP_201_CREATED)
def create_advance(
    payload: AdvanceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*WAREHOUSE_ROLES, *ACCOUNTS_ROLES)),
) -> AdvanceOut:
    if payload.freight_id and db.get(Freight, payload.freight_id) is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    advance = Advance(
        payee_type=payload.payee_type,
        driver_id=payload.driver_id,
        vehicle_owner_id=payload.vehicle_owner_id,
        freight_id=payload.freight_id,
        advance_date=payload.advance_date,
        amount=payload.amount,
        mode=payload.mode,
        reference=payload.reference,
        reason=payload.reason,
        status=AdvanceStatus.OUTSTANDING,
        issued_by_id=user.id,
    )
    db.add(advance)
    db.commit()
    db.refresh(advance)
    return _to_out(advance)


@router.get("/advances", response_model=list[AdvanceOut])
def list_advances(
    driver_id: str | None = None,
    vehicle_owner_id: str | None = None,
    outstanding_only: bool = False,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*BACK_OFFICE_ROLES)),
) -> list[AdvanceOut]:
    stmt = select(Advance)
    if driver_id:
        stmt = stmt.where(Advance.driver_id == driver_id)
    if vehicle_owner_id:
        stmt = stmt.where(Advance.vehicle_owner_id == vehicle_owner_id)
    if outstanding_only:
        stmt = stmt.where(
            Advance.status.in_([AdvanceStatus.OUTSTANDING, AdvanceStatus.PART_RECOVERED])
        )

    rows = db.execute(stmt.order_by(Advance.advance_date.desc())).scalars().all()
    return [_to_out(a) for a in rows]


@router.get("/freights/{freight_id}/account", response_model=list[TripAccountOut])
def trip_account(
    freight_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*BACK_OFFICE_ROLES)),
) -> list[TripAccountOut]:
    """What the trip owes, after the advance.

    Normally one account. A trip whose vehicle was swapped mid-run returns two,
    each covering only the legs that party actually ran.
    """
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    return [
        TripAccountOut(
            payee_type=a.payee_type,
            payee_id=a.payee_id,
            payee_name=a.payee_name,
            driver_names=a.driver_names,
            by_head=head_totals(a),
            gross=a.gross,
            advance_drawn=a.advance_drawn,
            advance_recovered=a.advance_recovered,
            balance_payable=a.balance_payable,
            advance_carried_forward=a.advance_carried_forward,
            is_closed=a.is_closed,
        )
        for a in trip_accounts(db, freight)
    ]
