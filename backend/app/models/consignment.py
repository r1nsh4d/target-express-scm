import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.consignee import Consignee
from app.models.enums import BoxStatus, ConsignmentStatus
from app.models.vendor import GoodsCategory, VendorDivision, VendorWarehouse


class Consignment(BaseModel):
    """One vendor bill, for one delivery point.

    The vendor's own bill number is what the warehouse crew and the consignee
    both recognise, so it is printed on every box label.
    """

    __tablename__ = "consignments"

    vendor_division_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_divisions.id"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_warehouses.id"), nullable=False
    )
    consignee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consignees.id"), nullable=False
    )
    goods_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_categories.id")
    )
    # Set once the consignment is assigned to a stop on a trip.
    freight_point_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freight_points.id", ondelete="SET NULL"), index=True
    )

    vendor_bill_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    declared_box_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    declared_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    eway_bill_no: Mapped[str | None] = mapped_column(String(32))
    remarks: Mapped[str | None] = mapped_column(Text)

    status: Mapped[ConsignmentStatus] = mapped_column(
        String(24), default=ConsignmentStatus.RECEIVED, nullable=False
    )

    vendor_division: Mapped[VendorDivision] = relationship()
    warehouse: Mapped[VendorWarehouse] = relationship()
    consignee: Mapped[Consignee] = relationship()
    goods_category: Mapped[GoodsCategory | None] = relationship()
    freight_point: Mapped["FreightPoint | None"] = relationship(  # noqa: F821
        back_populates="consignments"
    )
    boxes: Mapped[list["Box"]] = relationship(
        back_populates="consignment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Consignment {self.vendor_bill_no}>"


class Box(BaseModel):
    """One physical carton, and the atom the whole accountability story rests on.

    Counted and photographed into the vehicle, counted and photographed out at
    the point. The barcode supports an optional in-app scan where a vendor's
    cartons suit it; it is not required for the count to balance.
    """

    __tablename__ = "boxes"

    consignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consignments.id", ondelete="CASCADE"), nullable=False
    )
    item_no: Mapped[int] = mapped_column(Integer, nullable=False)
    barcode: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    # What the article is. Spare parts do not care, but furniture unloading is
    # priced per article - a chair and a wardrobe are different work - so this
    # is what the unloading rate is looked up by.
    item_code: Mapped[str | None] = mapped_column(String(48), index=True)
    item_name: Mapped[str | None] = mapped_column(String(160))

    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    dimensions: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[BoxStatus] = mapped_column(
        String(32), default=BoxStatus.SORTED, nullable=False
    )

    # When this exact carton was scanned off the vehicle at the point, and by
    # whom. The timestamp is the evidence: "the box was handed over" becomes
    # "box TE-A7K2M-003 was scanned at 14:07 by Rajesh at Anand Agencies".
    #
    # Nullable and will often stay null. Scanning is deliberately optional -
    # some vendors' cartons cannot take a sticker, and the count still has to
    # balance without it. A freight must never be blocked because a phone
    # camera would not focus.
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scanned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    remarks: Mapped[str | None] = mapped_column(Text)

    consignment: Mapped[Consignment] = relationship(back_populates="boxes")

    def __repr__(self) -> str:
        return f"<Box {self.barcode}>"
