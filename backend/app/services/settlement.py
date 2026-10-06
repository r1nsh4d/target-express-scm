"""Closing the money on a trip.

Rented vehicles run a per-trip cycle, not a monthly payment run:

    1. The owner draws an advance when the vehicle leaves.
    2. The trip runs; payouts are written head by head when the leg closes.
    3. The advance is recovered against those payouts and the balance is paid,
       which closes the trip's account.

Target Express pays the vehicle owner only on a rented trip. The driver is
recorded on every row and named on the document, but takes nothing from us -
the owner pays his own driver.

An advance larger than the trip earned is not an error: the excess stays
outstanding against that owner and is recovered from his next trip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AdvanceStatus, ChargeHead, PayeeType
from app.models.freight import Freight
from app.models.settlement import Advance, FreightPayout
from app.services.rating import money


@dataclass
class TripAccount:
    """What one payee earned on one trip, and what is left to pay them."""

    payee_type: PayeeType
    payee_id: str | None
    payee_name: str | None = None
    driver_names: list[str] = field(default_factory=list)

    by_head: dict[str, Decimal] = field(default_factory=dict)
    gross: Decimal = Decimal("0.00")
    advance_drawn: Decimal = Decimal("0.00")
    advance_recovered: Decimal = Decimal("0.00")

    @property
    def balance_payable(self) -> Decimal:
        """What still has to be handed over to close this trip."""
        return money(self.gross - self.advance_recovered)

    @property
    def advance_carried_forward(self) -> Decimal:
        """Advance the trip could not absorb, recovered from the next one."""
        return money(self.advance_drawn - self.advance_recovered)

    @property
    def is_closed(self) -> bool:
        return self.balance_payable == Decimal("0.00")


def _payee_key(row: FreightPayout) -> tuple[PayeeType, str | None]:
    if row.payee_type == PayeeType.VEHICLE_OWNER:
        owner_id = str(row.vehicle_owner_id) if row.vehicle_owner_id else None
        return (PayeeType.VEHICLE_OWNER, owner_id)
    return (PayeeType.DRIVER, str(row.driver_id))


def outstanding_advances(db: Session, freight_id) -> list[Advance]:
    return list(
        db.execute(
            select(Advance)
            .where(
                Advance.freight_id == freight_id,
                Advance.status.in_([AdvanceStatus.OUTSTANDING, AdvanceStatus.PART_RECOVERED]),
            )
            .order_by(Advance.advance_date)
        )
        .scalars()
        .all()
    )


def recover_advances_for_freight(db: Session, freight: Freight) -> list[Advance]:
    """Set the trip's advances against what it earned.

    Advances are matched to the payee who drew them, so an advance taken by a
    vehicle owner is never recovered from the driver who happened to be at the
    wheel. Oldest advance first.
    """
    payouts = (
        db.execute(select(FreightPayout).where(FreightPayout.freight_id == freight.id))
        .scalars()
        .all()
    )

    earned: dict[tuple[PayeeType, str | None], Decimal] = {}
    for row in payouts:
        key = _payee_key(row)
        earned[key] = earned.get(key, Decimal("0")) + Decimal(row.amount)

    touched: list[Advance] = []
    for advance in outstanding_advances(db, freight.id):
        key = (
            (PayeeType.VEHICLE_OWNER, str(advance.vehicle_owner_id))
            if advance.payee_type == PayeeType.VEHICLE_OWNER
            else (PayeeType.DRIVER, str(advance.driver_id))
        )
        available = earned.get(key, Decimal("0"))
        if available <= 0:
            continue

        recoverable = min(advance.outstanding, available)
        if recoverable <= 0:
            continue

        advance.recovered_amount = money(Decimal(advance.recovered_amount) + recoverable)
        advance.status = (
            AdvanceStatus.RECOVERED
            if advance.outstanding <= Decimal("0")
            else AdvanceStatus.PART_RECOVERED
        )
        earned[key] = available - recoverable
        touched.append(advance)

    db.flush()
    return touched


def trip_accounts(db: Session, freight: Freight) -> list[TripAccount]:
    """One account per payee on this trip.

    Normally a single account. A trip whose vehicle was swapped mid-run has two,
    each covering only the legs that party actually ran.
    """
    payouts = (
        db.execute(select(FreightPayout).where(FreightPayout.freight_id == freight.id))
        .scalars()
        .all()
    )

    accounts: dict[tuple[PayeeType, str | None], TripAccount] = {}

    for row in payouts:
        key = _payee_key(row)
        account = accounts.get(key)
        if account is None:
            account = TripAccount(payee_type=key[0], payee_id=key[1])
            accounts[key] = account

        head = str(row.head)
        account.by_head[head] = money(
            account.by_head.get(head, Decimal("0")) + Decimal(row.amount)
        )
        account.gross = money(Decimal(account.gross) + Decimal(row.amount))

    # Name the parties. The driver is listed even when the money goes to the
    # owner, because the settlement document shows both.
    for row in payouts:
        account = accounts[_payee_key(row)]
        if row.driver is not None and row.driver.name not in account.driver_names:
            account.driver_names.append(row.driver.name)
        if account.payee_type == PayeeType.VEHICLE_OWNER:
            owner = row.vehicle.owner if row.vehicle is not None else None
            if owner is not None:
                account.payee_name = owner.name
        elif row.driver is not None:
            account.payee_name = row.driver.name

    for advance in db.execute(
        select(Advance).where(Advance.freight_id == freight.id)
    ).scalars():
        key = (
            (PayeeType.VEHICLE_OWNER, str(advance.vehicle_owner_id))
            if advance.payee_type == PayeeType.VEHICLE_OWNER
            else (PayeeType.DRIVER, str(advance.driver_id))
        )
        account = accounts.get(key)
        if account is None:
            continue
        account.advance_drawn = money(Decimal(account.advance_drawn) + Decimal(advance.amount))
        account.advance_recovered = money(
            Decimal(account.advance_recovered) + Decimal(advance.recovered_amount)
        )

    return list(accounts.values())


def head_totals(account: TripAccount) -> dict[str, Decimal]:
    """Heads in a fixed order, zeros included, so a document prints the same
    rows every time."""
    order = [
        ChargeHead.TRANSPORTATION,
        ChargeHead.LOADING_UNLOADING,
        ChargeHead.POINT_INCENTIVE,
        ChargeHead.TOLL,
        ChargeHead.DETENTION,
        ChargeHead.OTHER,
    ]
    return {str(h): account.by_head.get(str(h), Decimal("0.00")) for h in order}
