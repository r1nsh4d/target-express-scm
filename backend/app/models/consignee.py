import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel
from app.models.enums import ConsigneeType, GeoConfidence


class Consignee(BaseModel):
    """End customer or a vendor's distribution centre.

    The pin a customer corrects from their tracking link is written back here,
    so the second delivery to the same address is already right.
    """

    __tablename__ = "consignees"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    type: Mapped[ConsigneeType] = mapped_column(
        String(32), default=ConsigneeType.RETAIL_CUSTOMER, nullable=False
    )
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    alternate_phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    district: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    pincode: Mapped[str | None] = mapped_column(String(10))

    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7))
    geo_confidence: Mapped[GeoConfidence] = mapped_column(
        String(24), default=GeoConfidence.UNVERIFIED, nullable=False
    )

    # Set when this consignee is the vendor's own distribution centre.
    parent_vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id")
    )

    landmark: Mapped[str | None] = mapped_column(Text)
    delivery_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Consignee {self.name}>"
