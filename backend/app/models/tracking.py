import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel
from app.models.enums import LocationChangeStatus


class TrackingSession(BaseModel):
    """The customer's no-login link for one delivery point.

    One per point, so a consignee only ever sees their own boxes.
    """

    __tablename__ = "tracking_sessions"

    freight_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freight_points.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sent_to_phone: Mapped[str | None] = mapped_column(String(20))
    sent_channel: Mapped[str | None] = mapped_column(String(16))  # WHATSAPP | SMS
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LocationChangeRequest(BaseModel):
    """Raised when a consignee corrects their drop pin.

    Anything beyond the auto-approve radius needs an admin decision, because
    the correction moves billable kilometres.
    """

    __tablename__ = "location_change_requests"

    freight_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freight_points.id", ondelete="CASCADE"), nullable=False
    )
    consignee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consignees.id"), nullable=False
    )

    old_latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    old_longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    new_latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    new_longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    distance_delta_m: Mapped[int | None] = mapped_column(Integer)

    new_address: Mapped[str | None] = mapped_column(Text)
    requested_note: Mapped[str | None] = mapped_column(Text)

    status: Mapped[LocationChangeStatus] = mapped_column(
        String(24), default=LocationChangeStatus.PENDING, nullable=False, index=True
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)


class VehiclePing(BaseModel):
    """GPS breadcrumb from the driver's phone.

    Buffered on the device when offline and backfilled, so `recorded_at` is the
    truth and `created_at` only says when it reached us.
    """

    __tablename__ = "vehicle_pings"

    freight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freights.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    leg_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freight_legs.id", ondelete="SET NULL")
    )
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    accuracy_m: Mapped[int | None] = mapped_column(Integer)
    speed_kmph: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
