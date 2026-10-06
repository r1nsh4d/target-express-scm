import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import ApprovalStatus, EntryMode, ExpenseType, PaidBy


class TripExpense(BaseModel):
    """Money paid or drawn on the road.

    `entered_by_id` and `entry_mode` matter: when the office keys an entry on a
    driver's behalf it still shows in his app, marked as office-entered, so
    nothing is recorded against him that he cannot see.
    """

    __tablename__ = "trip_expenses"

    freight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freights.id", ondelete="CASCADE"), nullable=False
    )
    leg_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freight_legs.id", ondelete="SET NULL")
    )
    freight_point_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freight_points.id", ondelete="SET NULL")
    )

    type: Mapped[ExpenseType] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    receipt_photo_url: Mapped[str | None] = mapped_column(String(500))
    paid_by: Mapped[PaidBy] = mapped_column(String(16), default=PaidBy.DRIVER, nullable=False)

    # Set on a LOADING expense: which helper at the godown was paid. Lets a
    # month's payments to one helper be totalled without reading every trip.
    labour_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("labour.id"), index=True
    )
    labour_count: Mapped[int | None] = mapped_column(Integer)

    # True when this expense is passed through onto the vendor's invoice
    # (tolls and detention are; a driver's meal is not).
    billable_to_vendor: Mapped[bool] = mapped_column(default=False, nullable=False)

    entered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    entry_mode: Mapped[EntryMode] = mapped_column(
        String(24), default=EntryMode.SELF, nullable=False
    )

    approval_status: Mapped[ApprovalStatus] = mapped_column(
        String(16), default=ApprovalStatus.PENDING, nullable=False, index=True
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    remarks: Mapped[str | None] = mapped_column(Text)

    freight: Mapped["Freight"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<TripExpense {self.type} {self.amount}>"
