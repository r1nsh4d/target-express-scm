import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import UnloadingBasis
from app.models.vendor import VendorDivision


class RateCard(BaseModel):
    """What a vendor division is billed per trip.

    Verified against Target Express invoices 191/2026-27/022 and /023 (Godrej):

        line_total = base_trip_amount
                   + max(0, km - included_km) * extra_km_rate
                   + max(0, points - included_points) * extra_point_rate
                   + toll + unloading + unloading_additional + detention

    with base 1867, included_km 60, extra_km_rate 17, included_points 3 and
    extra_point_rate 175. Those figures reconcile both invoices to the rupee.

    Cards are versioned by `effective_from`/`effective_to` and never edited in
    place, so re-printing an old invoice reproduces the original numbers.
    """

    __tablename__ = "rate_cards"
    __table_args__ = (
        UniqueConstraint(
            "vendor_division_id",
            "vehicle_type_id",
            "effective_from",
            name="uq_rate_card_division_type_from",
        ),
    )

    vendor_division_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendor_divisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # NULL means the card applies to every vehicle type, which is the Godrej case.
    vehicle_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle_types.id")
    )

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)

    base_trip_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    included_km: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_km_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # Points are charged as a slab: a fixed amount covering the first
    # `included_points` stops, then `extra_point_rate` for each stop beyond.
    #
    #   point_charge = base_point_charge
    #                + max(0, points - included_points) x extra_point_rate
    #
    # A vendor charging 500 for 3 points and 100 thereafter bills a 7-point trip
    # at 500 + 4 x 100 = 900.
    #
    # Godrej sets base_point_charge to 0 because their point allowance is
    # already inside the 1867 trip base - which is why their invoices still
    # reconcile with this field present.
    base_point_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    included_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_point_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # Unloading BILLED to the vendor. What the driver is PAID sits on
    # DriverPayTerms and is intentionally independent.
    unloading_basis: Mapped[UnloadingBasis] = mapped_column(
        String(24), default=UnloadingBasis.NOT_APPLICABLE, nullable=False
    )
    unloading_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    toll_pass_through: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    detention_pass_through: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    vendor_division: Mapped[VendorDivision] = relationship()

    def __repr__(self) -> str:
        return f"<RateCard division={self.vendor_division_id} from={self.effective_from}>"


class UnloadingItemRate(BaseModel):
    """Per-article unloading rates for furniture-type divisions.

    Furniture is not unloaded by the box: a chair, a wardrobe and a mattress are
    different work, and carrying any of them up four floors is different work
    again. So each article carries a ground-floor rate plus a charge for every
    floor above ground.

        charge = base_rate + floor x per_floor_rate

    A chair at 50 with 10 a floor, delivered to the 4th floor, unloads at 90.

    Versioned like a rate card, so re-printing an old invoice reproduces the
    rates that were in force on the day.
    """

    __tablename__ = "unloading_item_rates"
    __table_args__ = (
        UniqueConstraint(
            "vendor_division_id",
            "item_code",
            "effective_from",
            name="uq_unloading_item_division_code_from",
        ),
    )

    vendor_division_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendor_divisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_code: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String(160), nullable=False)

    base_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    per_floor_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # Charge floors even when the building has a lift. Carrying a wardrobe up
    # four flights and wheeling it into a lift are not the same job, so this is
    # a per-division commercial decision rather than a fixed rule.
    charge_floors_with_lift: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Some contracts stop counting beyond a certain height. 0 means no cap.
    max_chargeable_floors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    vendor_division: Mapped[VendorDivision] = relationship()

    def __repr__(self) -> str:
        return f"<UnloadingItemRate {self.item_code} {self.base_rate}+{self.per_floor_rate}/floor>"
