import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import (
    DriverEngagement,
    HireRateBasis,
    UnloadingShareBasis,
    VehicleOwnership,
)


class VehicleType(BaseModel):
    """DOST, 509F and so on.

    Printed on the vendor invoice header but, on the Godrej contracts, it does
    not change the rate: the same registrations bill identically across both
    divisions. Kept as an optional qualifier on the rate card in case a future
    vendor does price by type.
    """

    __tablename__ = "vehicle_types"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    capacity_kg: Mapped[int | None] = mapped_column(Integer)
    capacity_cbm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class VehicleOwner(BaseModel):
    """The party paid for a rented vehicle.

    Held separately from the vehicle because one owner commonly supplies several
    vehicles, and settlement and advances are per owner rather than per lorry.
    """

    __tablename__ = "vehicle_owners"

    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    alternate_phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    pan: Mapped[str | None] = mapped_column(String(10))
    gstin: Mapped[str | None] = mapped_column(String(15))
    bank_account: Mapped[str | None] = mapped_column(String(64))
    ifsc: Mapped[str | None] = mapped_column(String(16))
    bank_name: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="owner")

    def __repr__(self) -> str:
        return f"<VehicleOwner {self.name}>"


class Vehicle(BaseModel):
    """Owned by Target Express, or rented in from an outside owner.

    Each vehicle carries its own LR book, which is why LR numbers on a vendor
    invoice do not run in order.
    """

    __tablename__ = "vehicles"

    registration_no: Mapped[str] = mapped_column(
        String(24), unique=True, index=True, nullable=False
    )
    vehicle_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle_types.id")
    )
    ownership: Mapped[VehicleOwnership] = mapped_column(
        String(16), default=VehicleOwnership.OWNED, nullable=False
    )

    # Set for HIRED vehicles. This is who the money goes to for a rented trip.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicle_owners.id")
    )

    # LR book held against this vehicle. The application issues the next number
    # on dispatch; `lr_next_number` can be reset when a new physical book starts.
    lr_prefix: Mapped[str] = mapped_column(String(12), default="", nullable=False)
    lr_next_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Last closing odometer, kept denormalised so the continuity check on the
    # next dispatch is a single read.
    last_closing_km: Mapped[int | None] = mapped_column(Integer)

    insurance_expiry: Mapped[date | None] = mapped_column(Date)
    fitness_expiry: Mapped[date | None] = mapped_column(Date)
    permit_expiry: Mapped[date | None] = mapped_column(Date)
    puc_expiry: Mapped[date | None] = mapped_column(Date)

    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    vehicle_type: Mapped[VehicleType | None] = relationship()
    owner: Mapped[VehicleOwner | None] = relationship(back_populates="vehicles")
    hire_terms: Mapped[list["VehicleHireTerms"]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan"
    )

    @property
    def is_rented(self) -> bool:
        return self.ownership == VehicleOwnership.HIRED

    def __repr__(self) -> str:
        return f"<Vehicle {self.registration_no}>"


class VehicleHireTerms(BaseModel):
    """What Target Express pays the OWNER of a rented vehicle, head by head.

    Rent is a vehicle arrangement, not a driver one: the money settles to the
    owner, who pays his own driver. The driver's name still prints on the
    settlement document.

        TRANSPORTATION     rate_value, by rate_basis, with minimum_km_per_trip
        LOADING_UNLOADING  reimbursed at actuals unless includes_unloading
        POINT_INCENTIVE    per_point_amount x points, normally zero on rentals

    Versioned by effective_from/to, like a rate card.
    """

    __tablename__ = "vehicle_hire_terms"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    rate_basis: Mapped[HireRateBasis] = mapped_column(
        String(16), default=HireRateBasis.PER_KM, nullable=False
    )
    rate_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    minimum_km_per_trip: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # True when the agreed rent already covers unloading, so nothing is
    # reimbursed separately.
    includes_unloading: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    per_point_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # Unloading money goes to the driver by default even on a rented vehicle,
    # because he is the one who pays the labourers at the point and splits it
    # with the cleaner. The hire itself still settles to the owner. Flip this
    # where an owner insists on receiving the unloading too.
    unloading_paid_to_owner: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)

    vehicle: Mapped[Vehicle] = relationship(back_populates="hire_terms")


class Driver(BaseModel):
    """Operational record. Login credentials live on the linked `User`."""

    __tablename__ = "drivers"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    engagement: Mapped[DriverEngagement] = mapped_column(
        String(32), default=DriverEngagement.OWN_STAFF, nullable=False
    )
    licence_no: Mapped[str | None] = mapped_column(String(40))
    licence_expiry: Mapped[date | None] = mapped_column(Date)
    address: Mapped[str | None] = mapped_column(Text)
    bank_account: Mapped[str | None] = mapped_column(String(64))
    ifsc: Mapped[str | None] = mapped_column(String(16))

    # Vehicle this driver normally runs, if any.
    default_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    pay_terms: Mapped[list["DriverPayTerms"]] = relationship(
        back_populates="driver", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Driver {self.name}>"


class Labour(BaseModel):
    """Loading crew at a vendor warehouse.

    These are the helpers who load the vehicle at the godown, alongside the
    Target Express admin. Held as a master because it is largely the same few
    people every day, so the admin picks a name rather than retyping it, and a
    month's payments to one helper can be totalled.

    Unloading labour at the delivery end is not tracked here: that money goes to
    the driver as a lump and he splits it with the cleaner himself.
    """

    __tablename__ = "labour"

    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_warehouses.id")
    )
    daily_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    per_trip_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Labour {self.name}>"


class DriverPayTerms(BaseModel):
    """What the driver earns, head by head.

    In practice Target Express pays drivers on **distance**, plus the unloading
    cash where it applies - so `per_km_amount` and `unloading_share_percent` are
    the two that normally carry a value. The other fields default to zero and
    exist for drivers on a different arrangement.

        TRANSPORTATION     per_km_amount x km  (+ per_trip / daily allowance)
        LOADING_UNLOADING  unloading_share_percent of what was paid out
        POINT_INCENTIVE    per_point_amount - normally ZERO

    The heads mirror the vendor's billing heads so margin reads per head, but
    the amounts are independent. The point incentive the vendor is charged does
    not automatically reach the driver; that difference is margin Target Express
    keeps. Likewise, on spare-parts trips the vendor is billed nothing for
    unloading while money still goes out here.

    These apply when the trip ran on an OWNED vehicle. On a rented vehicle the
    hire goes to the vehicle owner under VehicleHireTerms - though the unloading
    cash still reaches the driver, who pays the labourers.
    """

    __tablename__ = "driver_pay_terms"

    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False
    )
    monthly_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    per_trip_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    per_km_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    daily_allowance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # The driver's point incentive can start after a threshold too, mirroring
    # the vendor side: 0 means every delivery point earns, 3 means only the
    # fourth stop onward does.
    incentive_after_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    per_point_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    # Share of the unloading amount the driver keeps, 0-100. Target Express
    # keeps the remainder - that is the margin on unloading.
    unloading_share_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    # ...a share of WHICH pot. See UnloadingShareBasis: billing the vendor 900
    # and giving the driver 70% is not the same money as reimbursing 70% of the
    # 600 he handed to the labourers, and both arrangements exist.
    unloading_share_basis: Mapped[UnloadingShareBasis] = mapped_column(
        String(20),
        default=UnloadingShareBasis.PAID_AT_POINT,
        # server_default, not just default. A Python-side default only runs on
        # an ORM insert; it does nothing for ALTER TABLE, so adding this column
        # NOT NULL to a table that already has pay terms in it fails outright.
        # Every driver already on the books keeps the behaviour they had.
        server_default=UnloadingShareBasis.PAID_AT_POINT.value,
        nullable=False,
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)

    driver: Mapped[Driver] = relationship(back_populates="pay_terms")
