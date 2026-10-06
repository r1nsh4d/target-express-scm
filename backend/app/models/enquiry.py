"""Business enquiries from the public website.

A vendor who lands on targetexpress.in and wants a quote has, until now, had no
way to reach the company except a phone number. This is that way: the form on
the landing page writes a row here, and the office works the list from inside
the application rather than from a mailbox nobody owns.

Nothing here is trusted. Every field is attacker-supplied, so every field is
length-bounded at the column and validated again at the schema.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel
from app.models.enums import EnquiryStatus


class Enquiry(BaseModel):
    __tablename__ = "enquiries"

    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(200))

    # What they move and from where. Free text on purpose: a first enquiry is
    # not the moment to make somebody pick from a dropdown.
    goods_type: Mapped[str | None] = mapped_column(String(120))
    origin_city: Mapped[str | None] = mapped_column(String(120))
    monthly_volume: Mapped[str | None] = mapped_column(String(120))
    message: Mapped[str | None] = mapped_column(Text)

    status: Mapped[EnquiryStatus] = mapped_column(
        String(20), default=EnquiryStatus.NEW, nullable=False, index=True
    )
    # Who in the office owns it, and what happened when they called.
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    internal_note: Mapped[str | None] = mapped_column(Text)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Kept for abuse handling: a burst from one address is the signal, and the
    # row itself is the evidence.
    source_ip: Mapped[str | None] = mapped_column(String(64))
    is_spam: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Enquiry {self.company_name}>"
