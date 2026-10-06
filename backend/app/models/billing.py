import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import InvoiceStatus
from app.models.vendor import VendorDivision


class VendorInvoice(BaseModel):
    """Tax invoice to a vendor division for a period.

    Mirrors the sheet Target Express issues today: a header carrying the
    division and vehicle type, then one annexure line per trip.
    """

    __tablename__ = "vendor_invoices"

    invoice_no: Mapped[str] = mapped_column(String(48), unique=True, index=True, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)

    vendor_division_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_divisions.id"), nullable=False
    )
    # Printed on the header. Descriptive only; it does not drive the rate.
    vehicle_type_label: Mapped[str | None] = mapped_column(String(64))

    taxable_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    cgst: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    sgst: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    igst: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    status: Mapped[InvoiceStatus] = mapped_column(
        String(16), default=InvoiceStatus.DRAFT, nullable=False, index=True
    )
    issued_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    remarks: Mapped[str | None] = mapped_column(Text)

    vendor_division: Mapped[VendorDivision] = relationship()
    lines: Mapped[list["VendorInvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="VendorInvoiceLine.sl_no"
    )

    def __repr__(self) -> str:
        return f"<VendorInvoice {self.invoice_no}>"


class VendorInvoiceLine(BaseModel):
    """One trip, one line.

    Every input to the arithmetic is stored on the line rather than looked up,
    so the invoice reprints identically years later and a vendor query can be
    answered from the line alone.
    """

    __tablename__ = "vendor_invoice_lines"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_invoices.id", ondelete="CASCADE"), nullable=False
    )
    freight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freights.id"), unique=True, nullable=False
    )

    sl_no: Mapped[int] = mapped_column(Integer, nullable=False)
    trip_date: Mapped[date] = mapped_column(Date, nullable=False)
    trip_no: Mapped[str] = mapped_column(String(32), nullable=False)
    lr_no: Mapped[str | None] = mapped_column(String(32))
    vehicle_no: Mapped[str] = mapped_column(String(24), nullable=False)
    destination_text: Mapped[str] = mapped_column(String(500), nullable=False)
    point_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    start_km: Mapped[int | None] = mapped_column(Integer)
    close_km: Mapped[int | None] = mapped_column(Integer)
    km: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    included_km: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_km: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_km_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    extra_km_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    included_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_point_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    extra_point_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    toll: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    unloading: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    unloading_additional: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, nullable=False
    )
    detention: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    # Its own column, never added into `unloading`. The vendor is reimbursing a
    # local demand, not paying for Target Express's unloading work, and the two
    # have to be arguable separately.
    coolie: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, server_default="0", nullable=False
    )

    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    invoice: Mapped[VendorInvoice] = relationship(back_populates="lines")

    def __repr__(self) -> str:
        return f"<VendorInvoiceLine {self.trip_no} {self.line_total}>"
