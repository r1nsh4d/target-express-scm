from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel
from app.models.enums import UserRole


class User(BaseModel):
    """Single login for every role: admins, accounts, drivers and stakeholders.

    A driver's operational record lives in `Driver`; this row only carries the
    credentials and the role that shapes what they can reach.
    """

    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Drivers on rented vehicles log in to run the trip but are not paid by
    # Target Express, so they have no earnings to see. Own drivers normally do.
    # Set per user rather than derived from the vehicle, because a driver can
    # move between an owned and a rented lorry from one week to the next and his
    # visibility should not flip with the roster.
    can_view_earnings: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<User {self.phone} {self.role}>"
