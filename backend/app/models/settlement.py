import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import AdvanceStatus, ChargeHead, PayeeType, SettlementStatus


class FreightPayout(BaseModel):
    """What one leg of a trip earns its payee, under one charge head.

    Written when a leg closes. One row per head per leg, so the payout mirrors
    the vendor invoice line head for head and margin can be read off directly.

    The payee is resolved from the leg's vehicle: an owned vehicle pays its
    driver, a rented vehicle pays the vehicle's owner. `driver_id` is recorded
    on every row regardless, because the settlement document names the driver
    even when the money goes to the owner.
    """

    __tablename__ = "freight_payouts"

    freight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freights.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    leg_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freight_legs.id", ondelete="CASCADE"), nullable=False
    )

    head: Mapped[ChargeHead] = mapped_column(String(32), nullable=False)

    payee_type: Mapped[PayeeType] = mapped_column(String(24), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False
    )
    vehicle_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle_owners.id")
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # Inputs the amount came from, kept so a settlement explains itself without
    # recomputation: km for transportation, point count for the incentive.
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    basis: Mapped[str | None] = mapped_column(String(120))

    settlement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("settlements.id"), index=True
    )

    def __repr__(self) -> str:
        return f"<FreightPayout {self.head} {self.amount} -> {self.payee_type}>"


class Advance(BaseModel):
    """Money handed over before a settlement, recovered against it.

    Advances run to a driver or to a vehicle owner, matching whoever the payee
    is for the work. An advance to an owner is recovered from that owner's hire
    settlement, not from the driver who happened to be at the wheel.
    """

    __tablename__ = "advances"

    payee_type: Mapped[PayeeType] = mapped_column(String(24), nullable=False)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drivers.id"), index=True
    )
    vehicle_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle_owners.id"), index=True
    )

    # Set when the advance was drawn against a particular trip.
    freight_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freights.id", ondelete="SET NULL")
    )

    advance_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    recovered_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    mode: Mapped[str | None] = mapped_column(String(32))  # CASH | UPI | BANK
    reference: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)

    status: Mapped[AdvanceStatus] = mapped_column(
        String(24), default=AdvanceStatus.OUTSTANDING, nullable=False, index=True
    )

    issued_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    @property
    def outstanding(self) -> Decimal:
        return Decimal(self.amount) - Decimal(self.recovered_amount)

    def __repr__(self) -> str:
        return f"<Advance {self.amount} {self.status}>"


class Settlement(BaseModel):
    """A payment run for one payee over a period.

    Gross is the sum of that payee's payouts, less advances recovered, giving
    net payable. For a rented vehicle the payee is the owner; the drivers who
    ran the trips are still listed on the document.
    """

    __tablename__ = "settlements"

    settlement_no: Mapped[str] = mapped_column(
        String(48), unique=True, index=True, nullable=False
    )
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)

    payee_type: Mapped[PayeeType] = mapped_column(String(24), nullable=False)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drivers.id")
    )
    vehicle_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle_owners.id")
    )

    trip_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_km: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    transportation_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    loading_unloading_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    point_incentive_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, nullable=False
    )
    other_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    advance_recovered: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    deductions: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    net_payable: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    status: Mapped[SettlementStatus] = mapped_column(
        String(16), default=SettlementStatus.DRAFT, nullable=False, index=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[str | None] = mapped_column(String(64))
    remarks: Mapped[str | None] = mapped_column(Text)

    prepared_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    payouts: Mapped[list[FreightPayout]] = relationship()

    def __repr__(self) -> str:
        return f"<Settlement {self.settlement_no} {self.net_payable}>"
