"""Saved routes — the office's own numbered rounds.

Target Express does not plan a fresh route every morning. The same rounds come
back week after week, and the office already names them: "No. 11" is a known
run with a known set of customers in a known order. Until now that knowledge
lived in one person's head and in an Excel sheet.

A preset is that round, written down: a name, a warehouse to leave from, and an
ordered list of delivery points. Building a freight from one copies the points
in; the admin then drops the customers who have nothing this week and adds any
extras. Twenty minutes of typing becomes thirty seconds of ticking.

Two design decisions worth stating:

  * A preset is a TEMPLATE, never a link. Creating a freight copies the points
    and then forgets where they came from. Editing "No. 11" next month must not
    reach back and alter a freight that was already run and invoiced.

  * The points hold a consignee, not an address. A customer who moves is
    corrected once, on the customer record, and every preset that includes them
    is right from the next run onward.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.consignee import Consignee


class RoutePreset(BaseModel):
    """A named, reusable round."""

    __tablename__ = "route_presets"

    # What the office calls it. "No. 11", "Kasaragod Tuesday", "North loop".
    # Free text on purpose: these names already exist and are not ours to tidy.
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # Which vendor's business this round serves. Optional, because a few rounds
    # are shared, but normally set — it is what filters the list down to the
    # handful of presets that could apply to the freight being created.
    vendor_division_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_divisions.id", ondelete="SET NULL")
    )
    # Where the round starts and, because a freight is only finished when the
    # vehicle is back, where it ends.
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_warehouses.id", ondelete="SET NULL")
    )

    # Planning aids, not billing inputs. The round-trip distance a preset
    # usually runs is what lets an admin sanity-check a quote before dispatch;
    # the real kilometres still come from the odometer.
    typical_round_trip_km: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # How often it has actually been used, so the list can put the rounds that
    # earn their keep at the top instead of ordering them alphabetically.
    times_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    points: Mapped[list["RoutePresetPoint"]] = relationship(
        back_populates="preset",
        cascade="all, delete-orphan",
        order_by="RoutePresetPoint.sequence",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RoutePreset {self.name}>"


class RoutePresetPoint(BaseModel):
    """One stop on a saved round."""

    __tablename__ = "route_preset_points"
    __table_args__ = (
        # The same customer twice in one preset is a mistake, not a round that
        # visits them twice — and it would silently inflate the billable point
        # count on every freight built from it.
        UniqueConstraint("preset_id", "consignee_id", name="uq_route_preset_point_consignee"),
    )

    preset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("route_presets.id", ondelete="CASCADE"), nullable=False
    )
    consignee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consignees.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # Defaults carried into the freight, because they are properties of the
    # delivery address that nobody should retype: a third-floor shop with no
    # lift is a third-floor shop with no lift every single week, and both
    # numbers are billable for furniture.
    default_floor_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    default_has_lift: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # "Ask for Shaji", "gate shuts at 1pm", "unload from the back lane".
    delivery_hint: Mapped[str | None] = mapped_column(Text)

    preset: Mapped[RoutePreset] = relationship(back_populates="points")
    consignee: Mapped[Consignee] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RoutePresetPoint {self.sequence} of {self.preset_id}>"
