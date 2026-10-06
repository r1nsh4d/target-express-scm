import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.consignee import Consignee
from app.models.enums import (
    FreightPointStatus,
    FreightStatus,
    LegChangeReason,
)
from app.models.fleet import Driver, Vehicle
from app.models.vendor import VendorDivision, VendorWarehouse


class Freight(BaseModel):
    """A trip: one origin warehouse, many drop points, one or more vehicles.

    Billing rolls up to the freight. Vehicle hire and driver pay compute per
    leg, which is how a mid-trip vehicle change produces two vehicle bills
    without changing the shape of the vendor's invoice.
    """

    __tablename__ = "freights"

    trip_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    # Issued from the dispatching vehicle's LR book at dispatch time.
    lr_no: Mapped[str | None] = mapped_column(String(32), index=True)

    trip_date: Mapped[date] = mapped_column(nullable=False, index=True)
    vendor_division_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_divisions.id"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_warehouses.id"), nullable=False
    )

    status: Mapped[FreightStatus] = mapped_column(
        String(24), default=FreightStatus.DRAFT, nullable=False, index=True
    )

    # Rendered from the points at dispatch and stored, so a later edit to a
    # consignee's name never changes an issued invoice.
    destination_text: Mapped[str | None] = mapped_column(String(500))
    point_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    total_km: Mapped[int | None] = mapped_column(Integer)

    # Rate card in force at dispatch, plus a frozen copy of its numbers.
    rate_card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rate_cards.id")
    )
    rate_snapshot: Mapped[dict | None] = mapped_column(JSONB)

    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A trip is not finished when the last point is delivered - it is finished
    # when the vehicle is back at the warehouse it left from. That is what makes
    # the billed kilometres a closed round trip and lets the odometer chain meet
    # the next trip's opening reading.
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    remarks: Mapped[str | None] = mapped_column(Text)

    vendor_division: Mapped[VendorDivision] = relationship()
    warehouse: Mapped[VendorWarehouse] = relationship()
    points: Mapped[list["FreightPoint"]] = relationship(
        back_populates="freight",
        cascade="all, delete-orphan",
        order_by="FreightPoint.sequence",
    )
    legs: Mapped[list["FreightLeg"]] = relationship(
        back_populates="freight",
        cascade="all, delete-orphan",
        order_by="FreightLeg.sequence",
    )

    @property
    def has_returned(self) -> bool:
        """Back at the origin warehouse: every leg closed with a final reading."""
        return bool(self.legs) and all(leg.end_odometer is not None for leg in self.legs)

    @property
    def billable_point_count(self) -> int:
        """Points the vendor is charged for.

        A failed delivery still counts: the vehicle went there, which is the
        work being paid for. Only a SKIPPED point - one pulled from the route
        before the vehicle set off - is excluded.
        """
        return sum(1 for p in self.points if p.status != FreightPointStatus.SKIPPED)

    @property
    def delivered_point_count(self) -> int:
        """Points where goods actually changed hands. Reporting, not billing."""
        return sum(
            1
            for p in self.points
            if p.status in (FreightPointStatus.DELIVERED, FreightPointStatus.PART_DELIVERED)
        )

    @property
    def round_trip_km(self) -> int:
        """Billable distance: the whole loop out and back, across every leg."""
        return sum(leg.leg_distance_km or 0 for leg in self.legs)

    def __repr__(self) -> str:
        return f"<Freight {self.trip_no}>"


class FreightPoint(BaseModel):
    """One stop. Carries its own loading and delivery evidence."""

    __tablename__ = "freight_points"

    freight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freights.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    consignee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consignees.id"), nullable=False
    )

    # Snapshot of the address as it stood when the trip was built.
    address_snapshot: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7))

    # Photo of the drop location itself, so the driver can recognise the place.
    reference_image_url: Mapped[str | None] = mapped_column(String(500))

    # Which floor the goods actually go to. Ground is 0. Furniture unloading is
    # charged per article plus a climb charge per floor, so this is a billable
    # fact, not a note - which is why the driver confirms it at the point rather
    # than it being assumed when the trip is planned.
    floor_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_lift: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    planned_eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Checkpoint 1 - into the vehicle.
    loaded_box_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    loading_photo_url: Mapped[str | None] = mapped_column(String(500))
    loading_short_reason: Mapped[str | None] = mapped_column(Text)

    # Checkpoint 2 - out at the point.
    delivered_box_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivery_photo_url: Mapped[str | None] = mapped_column(String(500))
    receiver_name: Mapped[str | None] = mapped_column(String(160))
    receiver_otp: Mapped[str | None] = mapped_column(String(10))
    otp_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signature_url: Mapped[str | None] = mapped_column(String(500))

    # Unloading: what the driver actually paid out at this point, and what the
    # vendor is billed for it. Deliberately two numbers.
    unloading_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    unloading_billed: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    # Coolie money, kept apart from unloading on purpose.
    #
    # At some markets and godowns a local porter gang controls who may unload.
    # They are not Target Express's crew and not on the unloading rate sheet;
    # they are a cash demand made at the point, which the driver settles and the
    # vendor reimburses. Folding it into unloading_paid would make the unloading
    # sheet look wrong and make "why has unloading gone up?" unanswerable.
    #
    # Two numbers again, for the same reason: what went out of the driver's
    # pocket is not automatically what the vendor agreed to reimburse.
    # server_default as well as default: these are added to a table that already
    # holds every delivery point ever made, and ALTER TABLE ... NOT NULL has no
    # idea about a Python default. Existing points correctly become zero.
    coolie_paid: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, server_default="0", nullable=False
    )
    coolie_billed: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, server_default="0", nullable=False
    )
    # Who demanded it and why. An unexplained cash line is the one a vendor
    # refuses, so the note is what makes it collectable.
    coolie_note: Mapped[str | None] = mapped_column(Text)

    status: Mapped[FreightPointStatus] = mapped_column(
        String(24), default=FreightPointStatus.PENDING, nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)

    freight: Mapped[Freight] = relationship(back_populates="points")
    consignee: Mapped[Consignee] = relationship()
    consignments: Mapped[list["Consignment"]] = relationship(  # noqa: F821
        back_populates="freight_point"
    )

    def __repr__(self) -> str:
        return f"<FreightPoint {self.sequence} of freight {self.freight_id}>"


class FreightLeg(BaseModel):
    """One vehicle-and-driver stretch of a trip.

    A trip normally has one leg. A breakdown closes the current leg and opens a
    second, so kilometres, hire and driver pay split correctly while the vendor
    still sees a single trip.
    """

    __tablename__ = "freight_legs"

    freight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freights.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False
    )
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False
    )

    from_point_sequence: Mapped[int | None] = mapped_column(Integer)
    to_point_sequence: Mapped[int | None] = mapped_column(Integer)

    start_odometer: Mapped[int | None] = mapped_column(Integer)
    start_odometer_photo_url: Mapped[str | None] = mapped_column(String(500))
    end_odometer: Mapped[int | None] = mapped_column(Integer)
    end_odometer_photo_url: Mapped[str | None] = mapped_column(String(500))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Derived from the odometer pair, stored so billing never recomputes it.
    leg_distance_km: Mapped[int | None] = mapped_column(Integer)

    change_reason: Mapped[LegChangeReason] = mapped_column(
        String(32), default=LegChangeReason.INITIAL, nullable=False
    )
    change_notes: Mapped[str | None] = mapped_column(Text)

    freight: Mapped[Freight] = relationship(back_populates="legs")
    vehicle: Mapped[Vehicle] = relationship()
    driver: Mapped[Driver] = relationship()

    def __repr__(self) -> str:
        return f"<FreightLeg {self.sequence} of freight {self.freight_id}>"
