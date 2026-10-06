"""The market vehicle phonebook.

When a vendor sends a requirement on WhatsApp, the first thing the admin does is
find a lorry. Today that means scrolling a phone's contacts for a name he half
remembers, and guessing what was paid last time.

This is that phonebook, with the two facts the phone cannot hold: what we paid
this supplier last time, and whether they turned up. It is deliberately NOT the
fleet. A row here is somebody who might send a lorry; `Vehicle` is a lorry that
actually ran a freight and has an odometer, an LR book and a settlement history.
A contact graduates into the fleet the first time it is used, and `vehicle_id`
records that it did.

Nothing here feeds billing. It is a tool for the ten minutes before a freight
exists.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import MarketVehicleStanding


class MarketVehicle(BaseModel):
    """A lorry, or a supplier of lorries, that can be hired in."""

    __tablename__ = "market_vehicles"

    # The person who answers the phone. This is the field that matters — the
    # registration is often not known until the lorry is on its way.
    contact_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    alternate_phone: Mapped[str | None] = mapped_column(String(20))

    # Nullable, because a broker supplies whatever is free that day rather than
    # one particular lorry.
    registration_no: Mapped[str | None] = mapped_column(String(24), index=True)
    vehicle_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle_types.id", ondelete="SET NULL")
    )
    # "Can do two DOSTs at a day's notice", "407 only". Free text, because the
    # useful version of this is always a sentence.
    capacity_note: Mapped[str | None] = mapped_column(Text)

    # Where they are based, which decides whether calling them is worth it at
    # all — a Kannur lorry is no use for a Kochi load leaving in two hours.
    base_city: Mapped[str | None] = mapped_column(String(120), index=True)
    operating_area: Mapped[str | None] = mapped_column(Text)

    # The memory the phone does not have. Last rate and last date together are
    # what stop the same supplier quoting a different number every month and
    # nobody noticing.
    last_hired_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    last_hired_on: Mapped[date | None] = mapped_column(Date)
    times_hired: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Did they turn up. Three states rather than a star rating: the only
    # question an admin actually asks at 7am is "can I rely on this one".
    standing: Mapped[MarketVehicleStanding] = mapped_column(
        String(16), default=MarketVehicleStanding.UNTRIED, nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    # Payment details, kept here so a first hire does not stall while somebody
    # hunts for a bank account. Copied onto the VehicleOwner when one is made.
    pan: Mapped[str | None] = mapped_column(String(10))
    bank_account: Mapped[str | None] = mapped_column(String(64))
    ifsc: Mapped[str | None] = mapped_column(String(16))

    # Set once this contact has been turned into a real fleet vehicle, so the
    # phonebook entry and the lorry that ran the freight are the same thing.
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL")
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle_owners.id", ondelete="SET NULL")
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    vehicle_type = relationship("VehicleType")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MarketVehicle {self.contact_name} {self.registration_no or ''}>"
