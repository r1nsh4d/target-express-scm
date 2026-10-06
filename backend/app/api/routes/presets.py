"""Route presets and the market vehicle phonebook.

Both exist to serve the ten minutes before a freight exists: the vendor's
requirement arrives on WhatsApp, a lorry has to be found, and a round has to be
planned. Everything else in this application is about what happens after that.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import WAREHOUSE_ROLES, require_roles
from app.db.session import get_db
from app.models.consignee import Consignee
from app.models.enums import MarketVehicleStanding
from app.models.market_vehicle import MarketVehicle
from app.models.route_preset import RoutePreset, RoutePresetPoint
from app.schemas.base import ORMModel

router = APIRouter(
    prefix="/api",
    tags=["planning"],
    dependencies=[Depends(require_roles(*WAREHOUSE_ROLES))],
)


# ---------------------------------------------------------------------------
# Route presets
# ---------------------------------------------------------------------------


class PresetPointIn(BaseModel):
    consignee_id: str
    default_floor_number: int = Field(default=0, ge=0, le=99)
    default_has_lift: bool = False
    delivery_hint: str | None = Field(default=None, max_length=2000)


class PresetPointOut(ORMModel):
    id: str
    consignee_id: str
    consignee_name: str
    consignee_city: str | None
    consignee_phone: str | None
    sequence: int
    default_floor_number: int
    default_has_lift: bool
    delivery_hint: str | None


class PresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    vendor_division_id: str | None = None
    warehouse_id: str | None = None
    typical_round_trip_km: int | None = Field(default=None, ge=0, le=10_000)
    notes: str | None = Field(default=None, max_length=4000)
    # The whole point list, in order. Sent entire on every save rather than
    # patched stop by stop: reordering a round is the common edit, and a
    # sequence of add/move/remove calls would leave the order half-applied if
    # one of them failed.
    points: list[PresetPointIn] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _tidy(cls, v: str) -> str:
        return v.strip()

    @field_validator("points")
    @classmethod
    def _no_duplicate_consignees(cls, v: list[PresetPointIn]) -> list[PresetPointIn]:
        ids = [p.consignee_id for p in v]
        if len(ids) != len(set(ids)):
            # Silently deduplicating would quietly change the billable point
            # count on every freight built from this preset.
            raise ValueError("The same customer appears twice in this route")
        return v


class PresetOut(ORMModel):
    id: str
    name: str
    vendor_division_id: str | None
    warehouse_id: str | None
    typical_round_trip_km: int | None
    notes: str | None
    is_active: bool
    times_used: int
    points: list[PresetPointOut]


def _out(preset: RoutePreset) -> PresetOut:
    return PresetOut(
        id=str(preset.id),
        name=preset.name,
        vendor_division_id=str(preset.vendor_division_id) if preset.vendor_division_id else None,
        warehouse_id=str(preset.warehouse_id) if preset.warehouse_id else None,
        typical_round_trip_km=preset.typical_round_trip_km,
        notes=preset.notes,
        is_active=preset.is_active,
        times_used=preset.times_used,
        points=[
            PresetPointOut(
                id=str(p.id),
                consignee_id=str(p.consignee_id),
                consignee_name=p.consignee.name if p.consignee else "—",
                consignee_city=p.consignee.city if p.consignee else None,
                consignee_phone=p.consignee.phone if p.consignee else None,
                sequence=p.sequence,
                default_floor_number=p.default_floor_number,
                default_has_lift=p.default_has_lift,
                delivery_hint=p.delivery_hint,
            )
            for p in sorted(preset.points, key=lambda x: x.sequence)
        ],
    )


def _load(db: Session, preset_id: uuid.UUID) -> RoutePreset:
    preset = db.execute(
        select(RoutePreset)
        .options(joinedload(RoutePreset.points).joinedload(RoutePresetPoint.consignee))
        .where(RoutePreset.id == preset_id)
    ).unique().scalar_one_or_none()
    if preset is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return preset


def _apply_points(db: Session, preset: RoutePreset, points: list[PresetPointIn]) -> None:
    """Replace the whole stop list, renumbering from 1.

    Sequence is assigned here rather than accepted from the client, so a gap or
    a duplicate in what was sent cannot become a gap or duplicate in the round.
    """
    wanted = [uuid.UUID(p.consignee_id) for p in points]
    if wanted:
        found = set(
            db.execute(select(Consignee.id).where(Consignee.id.in_(wanted))).scalars().all()
        )
        missing = [str(c) for c in wanted if c not in found]
        if missing:
            raise HTTPException(
                status_code=400,
                detail="One of the customers on this route no longer exists",
            )

    preset.points.clear()
    db.flush()
    for i, p in enumerate(points, start=1):
        preset.points.append(
            RoutePresetPoint(
                consignee_id=uuid.UUID(p.consignee_id),
                sequence=i,
                default_floor_number=p.default_floor_number,
                default_has_lift=p.default_has_lift,
                delivery_hint=(p.delivery_hint or "").strip() or None,
            )
        )


@router.get("/route-presets", response_model=list[PresetOut])
def list_presets(
    vendor_division_id: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> list[PresetOut]:
    """Most-used first. A round run weekly should not sit below one used once."""
    stmt = (
        select(RoutePreset)
        .options(joinedload(RoutePreset.points).joinedload(RoutePresetPoint.consignee))
        .order_by(RoutePreset.times_used.desc(), RoutePreset.name)
    )
    if not include_inactive:
        stmt = stmt.where(RoutePreset.is_active.is_(True))
    if vendor_division_id:
        # A shared round (no division) stays visible whatever is being planned.
        stmt = stmt.where(
            or_(
                RoutePreset.vendor_division_id == uuid.UUID(vendor_division_id),
                RoutePreset.vendor_division_id.is_(None),
            )
        )
    presets = db.execute(stmt).unique().scalars().all()
    return [_out(p) for p in presets]


@router.post("/route-presets", response_model=PresetOut, status_code=201)
def create_preset(payload: PresetIn, db: Session = Depends(get_db)) -> PresetOut:
    preset = RoutePreset(
        name=payload.name,
        vendor_division_id=uuid.UUID(payload.vendor_division_id)
        if payload.vendor_division_id
        else None,
        warehouse_id=uuid.UUID(payload.warehouse_id) if payload.warehouse_id else None,
        typical_round_trip_km=payload.typical_round_trip_km,
        notes=(payload.notes or "").strip() or None,
    )
    db.add(preset)
    db.flush()
    _apply_points(db, preset, payload.points)
    db.commit()
    return _out(_load(db, preset.id))


@router.get("/route-presets/{preset_id}", response_model=PresetOut)
def get_preset(preset_id: uuid.UUID, db: Session = Depends(get_db)) -> PresetOut:
    return _out(_load(db, preset_id))


@router.put("/route-presets/{preset_id}", response_model=PresetOut)
def update_preset(
    preset_id: uuid.UUID, payload: PresetIn, db: Session = Depends(get_db)
) -> PresetOut:
    """Editing a round never reaches a freight already built from it.

    A preset is a template that is copied at creation time, not a link. "No. 11"
    gaining a stop in March must not change what a freight run in February
    delivered — that freight has been invoiced.
    """
    preset = _load(db, preset_id)
    preset.name = payload.name
    preset.vendor_division_id = (
        uuid.UUID(payload.vendor_division_id) if payload.vendor_division_id else None
    )
    preset.warehouse_id = uuid.UUID(payload.warehouse_id) if payload.warehouse_id else None
    preset.typical_round_trip_km = payload.typical_round_trip_km
    preset.notes = (payload.notes or "").strip() or None
    _apply_points(db, preset, payload.points)
    db.commit()
    return _out(_load(db, preset_id))


@router.delete("/route-presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_preset(preset_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    """Retired, not deleted. A round that stops running this season usually
    comes back, and its stop order is the thing nobody wants to rebuild."""
    preset = _load(db, preset_id)
    preset.is_active = False
    db.commit()


@router.post("/route-presets/{preset_id}/restore", response_model=PresetOut)
def restore_preset(preset_id: uuid.UUID, db: Session = Depends(get_db)) -> PresetOut:
    preset = _load(db, preset_id)
    preset.is_active = True
    db.commit()
    return _out(_load(db, preset_id))


class PresetUsed(BaseModel):
    times_used: int


@router.post("/route-presets/{preset_id}/used", response_model=PresetUsed)
def mark_used(preset_id: uuid.UUID, db: Session = Depends(get_db)) -> PresetUsed:
    """Called when a freight is actually created from this round.

    Separate from freight creation because a freight does not belong to a
    preset — it was only started from one. This is the single fact worth
    keeping, and it is what orders the list.
    """
    preset = _load(db, preset_id)
    preset.times_used += 1
    db.commit()
    return PresetUsed(times_used=preset.times_used)


# ---------------------------------------------------------------------------
# Market vehicle phonebook
# ---------------------------------------------------------------------------


class MarketVehicleIn(BaseModel):
    contact_name: str = Field(min_length=2, max_length=180)
    phone: str = Field(min_length=6, max_length=20)
    alternate_phone: str | None = Field(default=None, max_length=20)
    registration_no: str | None = Field(default=None, max_length=24)
    vehicle_type_id: str | None = None
    capacity_note: str | None = Field(default=None, max_length=1000)
    base_city: str | None = Field(default=None, max_length=120)
    operating_area: str | None = Field(default=None, max_length=1000)
    last_hired_rate: Decimal | None = Field(default=None, ge=0)
    last_hired_on: date | None = None
    standing: MarketVehicleStanding = MarketVehicleStanding.UNTRIED
    notes: str | None = Field(default=None, max_length=4000)
    pan: str | None = Field(default=None, max_length=10)
    bank_account: str | None = Field(default=None, max_length=64)
    ifsc: str | None = Field(default=None, max_length=16)

    @field_validator("registration_no")
    @classmethod
    def _plate(cls, v: str | None) -> str | None:
        # Registrations get typed as "kl 07 aa 1234" and searched as "KL07AA1234".
        return "".join((v or "").split()).upper() or None


class MarketVehicleOut(ORMModel):
    id: str
    contact_name: str
    phone: str
    alternate_phone: str | None
    registration_no: str | None
    vehicle_type_id: str | None
    vehicle_type_name: str | None
    capacity_note: str | None
    base_city: str | None
    operating_area: str | None
    last_hired_rate: Decimal | None
    last_hired_on: date | None
    times_hired: int
    standing: MarketVehicleStanding
    notes: str | None
    pan: str | None
    bank_account: str | None
    ifsc: str | None
    is_active: bool


def _mv_out(row: MarketVehicle) -> MarketVehicleOut:
    return MarketVehicleOut(
        id=str(row.id),
        contact_name=row.contact_name,
        phone=row.phone,
        alternate_phone=row.alternate_phone,
        registration_no=row.registration_no,
        vehicle_type_id=str(row.vehicle_type_id) if row.vehicle_type_id else None,
        vehicle_type_name=row.vehicle_type.name if row.vehicle_type else None,
        capacity_note=row.capacity_note,
        base_city=row.base_city,
        operating_area=row.operating_area,
        last_hired_rate=row.last_hired_rate,
        last_hired_on=row.last_hired_on,
        times_hired=row.times_hired,
        standing=row.standing,
        notes=row.notes,
        pan=row.pan,
        bank_account=row.bank_account,
        ifsc=row.ifsc,
        is_active=row.is_active,
    )


@router.get("/market-vehicles", response_model=list[MarketVehicleOut])
def list_market_vehicles(
    q: str | None = None,
    vehicle_type_id: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> list[MarketVehicleOut]:
    """Reliable first, then whoever was hired most recently.

    That ordering is the product: at 7am with a load waiting, the person who
    turned up last time is the right first call.
    """
    stmt = select(MarketVehicle).options(joinedload(MarketVehicle.vehicle_type))

    if not include_inactive:
        stmt = stmt.where(MarketVehicle.is_active.is_(True))
    if vehicle_type_id:
        stmt = stmt.where(MarketVehicle.vehicle_type_id == uuid.UUID(vehicle_type_id))
    if q:
        like = f"%{q.strip()}%"
        plate = "".join(q.split()).upper()
        stmt = stmt.where(
            or_(
                MarketVehicle.contact_name.ilike(like),
                MarketVehicle.phone.ilike(like),
                MarketVehicle.base_city.ilike(like),
                MarketVehicle.registration_no.ilike(f"%{plate}%"),
            )
        )

    # Reliable first, avoid last. An explicit CASE rather than ordering by the
    # column, which is a string and would sort AVOID to the top alphabetically.
    standing_rank = case(
        (MarketVehicle.standing == MarketVehicleStanding.RELIABLE, 0),
        (MarketVehicle.standing == MarketVehicleStanding.UNTRIED, 1),
        else_=2,
    )

    rows = (
        db.execute(
            stmt.order_by(
                standing_rank,
                MarketVehicle.last_hired_on.desc().nullslast(),
                MarketVehicle.contact_name,
            )
        )
        .unique()
        .scalars()
        .all()
    )
    return [_mv_out(r) for r in rows]


@router.post("/market-vehicles", response_model=MarketVehicleOut, status_code=201)
def create_market_vehicle(
    payload: MarketVehicleIn, db: Session = Depends(get_db)
) -> MarketVehicleOut:
    row = MarketVehicle(**payload.model_dump(exclude={"vehicle_type_id"}))
    row.vehicle_type_id = uuid.UUID(payload.vehicle_type_id) if payload.vehicle_type_id else None
    db.add(row)
    db.commit()
    db.refresh(row)
    return _mv_out(row)


@router.put("/market-vehicles/{row_id}", response_model=MarketVehicleOut)
def update_market_vehicle(
    row_id: uuid.UUID, payload: MarketVehicleIn, db: Session = Depends(get_db)
) -> MarketVehicleOut:
    row = db.get(MarketVehicle, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not in the phonebook")
    for key, value in payload.model_dump(exclude={"vehicle_type_id"}).items():
        setattr(row, key, value)
    row.vehicle_type_id = uuid.UUID(payload.vehicle_type_id) if payload.vehicle_type_id else None
    db.commit()
    db.refresh(row)
    return _mv_out(row)


class HiredIn(BaseModel):
    rate: Decimal = Field(ge=0)
    hired_on: date | None = None


@router.post("/market-vehicles/{row_id}/hired", response_model=MarketVehicleOut)
def record_hire(
    row_id: uuid.UUID, payload: HiredIn, db: Session = Depends(get_db)
) -> MarketVehicleOut:
    """Record that this supplier was used, and at what rate.

    This is the memory the phone does not have. Without it the same supplier
    quotes a different number every month and nobody notices.
    """
    row = db.get(MarketVehicle, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not in the phonebook")

    row.last_hired_rate = payload.rate
    row.last_hired_on = payload.hired_on or date.today()
    row.times_hired += 1
    # A supplier who has actually turned up is no longer untried. An explicit
    # AVOID is left alone — that judgement was made by a person.
    if row.standing == MarketVehicleStanding.UNTRIED:
        row.standing = MarketVehicleStanding.RELIABLE

    db.commit()
    db.refresh(row)
    return _mv_out(row)


@router.delete("/market-vehicles/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_market_vehicle(row_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    row = db.get(MarketVehicle, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not in the phonebook")
    row.is_active = False
    db.commit()
