import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
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

    # Who to ask for at the gate.
    #
    # "Kottayam Furniture Mart" is a shop and somebody answers its phone;
    # "Rinshad Km" is a person and the same field means something else. A
    # distributor has a purchase manager whose name is what the driver asks
    # for, and with nowhere to write it, it went into the delivery notes.
    contact_person: Mapped[str | None] = mapped_column(String(160))

    landmark: Mapped[str | None] = mapped_column(Text)
    delivery_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- completing the record, by the person who knows ------------------- #
    #
    # A customer entered during a morning's bills has a name, a mobile and a
    # town, because that is what the warehouse has and all it has time for.
    # The address, the landmark and the pin belong to the customer, and the
    # only practical way to ask is to send them a link.
    #
    # One token, one record, with an expiry. It is a link to correct your own
    # delivery address, not a login — it reaches nothing else and grants
    # nothing beyond the one consignee it was minted for.
    details_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    details_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    details_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Consignee {self.name}>"
