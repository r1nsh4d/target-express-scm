import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class GoodsCategory(BaseModel):
    """Spare parts, furniture, appliances and so on.

    Handling attributes here inform sorting and labelling; the money side is
    driven by the rate card attached to a vendor division.
    """

    __tablename__ = "goods_categories"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    is_fragile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_bulky: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Vendor(BaseModel):
    """The goods owner. Godrej is one vendor with several divisions."""

    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(15))
    pan: Mapped[str | None] = mapped_column(String(10))
    billing_address: Mapped[str | None] = mapped_column(Text)
    contact_person: Mapped[str | None] = mapped_column(String(120))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    payment_terms_days: Mapped[int] = mapped_column(default=30, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    divisions: Mapped[list["VendorDivision"]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )
    warehouses: Mapped[list["VendorWarehouse"]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )


class VendorDivision(BaseModel):
    """The billing unit, e.g. GODREJ OCP or GODREJ APPLIANCE SPARE.

    Rate cards hang off the division, not the vendor: the two Godrej divisions
    bill identical distance rates but differ on unloading.
    """

    __tablename__ = "vendor_divisions"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    goods_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_categories.id")
    )
    gstin: Mapped[str | None] = mapped_column(String(15))
    billing_address: Mapped[str | None] = mapped_column(Text)
    invoice_series: Mapped[str] = mapped_column(String(32), default="191", nullable=False)
    place_of_supply_state_code: Mapped[str | None] = mapped_column(String(2))
    gst_rate_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=12, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    vendor: Mapped[Vendor] = relationship(back_populates="divisions")
    goods_category: Mapped[GoodsCategory | None] = relationship()

    def __repr__(self) -> str:
        return f"<VendorDivision {self.code}>"


class VendorWarehouse(BaseModel):
    """Origin godown. Trips start and finish here, which is what makes the
    odometer chain closeable."""

    __tablename__ = "vendor_warehouses"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    vendor: Mapped[Vendor] = relationship(back_populates="warehouses")
