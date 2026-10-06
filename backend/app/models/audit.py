import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class OdometerCorrection(BaseModel):
    """An admin change to a meter reading, kept as its own record.

    The driver's original entry is never overwritten: a vendor query months
    later has to be able to show what was captured against what was billed.
    """

    __tablename__ = "odometer_corrections"

    leg_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freight_legs.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(String(24), nullable=False)  # start_odometer | end_odometer
    original_value: Mapped[int | None] = mapped_column(Integer)
    corrected_value: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    corrected_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    corrected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog(BaseModel):
    """Append-only trail of consequential changes."""

    __tablename__ = "audit_logs"

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    changes: Mapped[dict | None] = mapped_column(JSONB)

    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    actor_label: Mapped[str | None] = mapped_column(String(160))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
