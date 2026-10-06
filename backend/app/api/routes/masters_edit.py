"""Editing and retiring the master records.

Until now every master was create-only. A driver's name typed wrong stayed wrong
forever, a customer who moved could not be corrected, a lorry sold last month
still appeared in the assign list. That is not a missing nicety; it makes the
data drift away from reality, and once people stop trusting the list they go
back to the spreadsheet.

Two deliberate shapes here:

RETIRE, NOT DELETE
    Everything is referenced by something: a driver by a leg, a customer by a
    delivery point, a vehicle by an odometer chain. Deleting the row would
    either fail on a foreign key or — worse — orphan an invoice that has already
    been sent. So `DELETE` sets `is_active = false`. The record stops appearing
    in pickers and keeps answering for the history it is part of.

    A hard delete is offered only where nothing points at the row yet, and the
    endpoint checks rather than assumes.

RATE CARDS ARE NOT EDITABLE
    A rate agreed in April must still price an April freight in December. Cards
    are held per division and per date and a change is a NEW card from the day
    it starts — editing one would silently reprice work already invoiced. They
    can be retired, which stops them applying to future freights, and that is
    all. This is the one place where "you cannot edit this" is the feature.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_ROLES, WAREHOUSE_ROLES, require_roles
from app.db.session import get_db
from app.models.consignee import Consignee
from app.models.consignment import Consignment
from app.models.fleet import (
    Driver,
    Labour,
    Vehicle,
    VehicleOwner,
    VehicleType,
)
from app.models.freight import Freight, FreightLeg, FreightPoint
from app.models.rating import RateCard, UnloadingItemRate
from app.models.user import User
from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

router = APIRouter(prefix="/api", tags=["masters"])

WriteDep = Depends(require_roles(*ADMIN_ROLES))
OpsDep = Depends(require_roles(*WAREHOUSE_ROLES))


def _load(db: Session, model, obj_id: uuid.UUID, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    return obj


def _apply(obj, payload: BaseModel) -> None:
    """Only the fields that were actually sent.

    `exclude_unset` matters: a PATCH that omits `phone` must leave the phone
    alone, not blank it. Without this, every partial edit would quietly wipe
    whatever the form did not happen to include.
    """
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)


def _retire(db: Session, model, obj_id: uuid.UUID, label: str):
    obj = _load(db, model, obj_id, label)
    obj.is_active = False
    db.commit()
    return obj


def _restore(db: Session, model, obj_id: uuid.UUID, label: str):
    obj = _load(db, model, obj_id, label)
    obj.is_active = True
    db.commit()
    db.refresh(obj)
    return obj


def _in_use(db: Session, column, value) -> int:
    return int(db.execute(select(func.count()).where(column == value)).scalar() or 0)


# --------------------------------------------------------------------------- #
# Goods categories                                                            #
# --------------------------------------------------------------------------- #


class GoodsCategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, min_length=1, max_length=48)
    is_fragile: bool | None = None
    is_bulky: bool | None = None
    is_active: bool | None = None


@router.patch("/goods-categories/{item_id}")
def update_goods_category(
    item_id: uuid.UUID, payload: GoodsCategoryPatch, db: Session = Depends(get_db), _=WriteDep
):
    obj = _load(db, GoodsCategory, item_id, "Category")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/goods-categories/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_goods_category(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    _retire(db, GoodsCategory, item_id, "Category")


# --------------------------------------------------------------------------- #
# Vendors, divisions, warehouses                                              #
# --------------------------------------------------------------------------- #


class VendorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    gstin: str | None = Field(default=None, max_length=15)
    contact_person: str | None = Field(default=None, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=20)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    is_active: bool | None = None


@router.patch("/vendors/{item_id}")
def update_vendor(
    item_id: uuid.UUID, payload: VendorPatch, db: Session = Depends(get_db), _=WriteDep
):
    obj = _load(db, Vendor, item_id, "Vendor")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/vendors/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_vendor(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    _retire(db, Vendor, item_id, "Vendor")


@router.post("/vendors/{item_id}/restore")
def restore_vendor(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    obj = _restore(db, Vendor, item_id, "Vendor")
    return {"id": str(obj.id), "is_active": obj.is_active}


class VendorDivisionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, min_length=1, max_length=64)
    goods_category_id: str | None = None
    invoice_series: str | None = Field(default=None, max_length=32)
    gst_rate_percent: Decimal | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None


@router.patch("/vendor-divisions/{item_id}")
def update_vendor_division(
    item_id: uuid.UUID, payload: VendorDivisionPatch, db: Session = Depends(get_db), _=WriteDep
):
    obj = _load(db, VendorDivision, item_id, "Division")
    data = payload.model_dump(exclude_unset=True)
    if "goods_category_id" in data and data["goods_category_id"]:
        data["goods_category_id"] = uuid.UUID(data["goods_category_id"])
    for field, value in data.items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/vendor-divisions/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_vendor_division(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    _retire(db, VendorDivision, item_id, "Division")


class WarehousePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, min_length=1, max_length=48)
    address: str | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    is_active: bool | None = None


@router.patch("/warehouses/{item_id}")
def update_warehouse(
    item_id: uuid.UUID, payload: WarehousePatch, db: Session = Depends(get_db), _=WriteDep
):
    obj = _load(db, VendorWarehouse, item_id, "Warehouse")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/warehouses/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_warehouse(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    _retire(db, VendorWarehouse, item_id, "Warehouse")


# --------------------------------------------------------------------------- #
# Customers                                                                   #
# --------------------------------------------------------------------------- #


class ConsigneePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    alternate_phone: str | None = Field(default=None, max_length=20)
    address: str | None = None
    city: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=10)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    landmark: str | None = None
    delivery_notes: str | None = None
    is_active: bool | None = None


@router.patch("/consignees/{item_id}")
def update_consignee(
    item_id: uuid.UUID, payload: ConsigneePatch, db: Session = Depends(get_db), _=OpsDep
):
    """Correcting a customer fixes them for every FUTURE delivery.

    Freights already built hold a snapshot of the address they were dispatched
    against, so this cannot rewrite what a past run was told to do.
    """
    obj = _load(db, Consignee, item_id, "Customer")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/consignees/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_consignee(item_id: uuid.UUID, db: Session = Depends(get_db), _=OpsDep):
    _retire(db, Consignee, item_id, "Customer")


@router.post("/consignees/{item_id}/restore")
def restore_consignee(item_id: uuid.UUID, db: Session = Depends(get_db), _=OpsDep):
    obj = _restore(db, Consignee, item_id, "Customer")
    return {"id": str(obj.id), "is_active": obj.is_active}


# --------------------------------------------------------------------------- #
# Fleet                                                                        #
# --------------------------------------------------------------------------- #


class VehicleTypePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    capacity_kg: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


@router.patch("/vehicle-types/{item_id}")
def update_vehicle_type(
    item_id: uuid.UUID, payload: VehicleTypePatch, db: Session = Depends(get_db), _=WriteDep
):
    obj = _load(db, VehicleType, item_id, "Vehicle type")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/vehicle-types/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_vehicle_type(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    _retire(db, VehicleType, item_id, "Vehicle type")


class VehicleOwnerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    phone: str | None = Field(default=None, max_length=20)
    alternate_phone: str | None = Field(default=None, max_length=20)
    address: str | None = None
    pan: str | None = Field(default=None, max_length=10)
    gstin: str | None = Field(default=None, max_length=15)
    bank_account: str | None = Field(default=None, max_length=64)
    ifsc: str | None = Field(default=None, max_length=16)
    notes: str | None = None
    is_active: bool | None = None


@router.patch("/vehicle-owners/{item_id}")
def update_vehicle_owner(
    item_id: uuid.UUID, payload: VehicleOwnerPatch, db: Session = Depends(get_db), _=WriteDep
):
    obj = _load(db, VehicleOwner, item_id, "Vehicle owner")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/vehicle-owners/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_vehicle_owner(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    _retire(db, VehicleOwner, item_id, "Vehicle owner")


class VehiclePatch(BaseModel):
    registration_no: str | None = Field(default=None, min_length=4, max_length=24)
    vehicle_type_id: str | None = None
    owner_id: str | None = None
    lr_prefix: str | None = Field(default=None, max_length=12)
    make_model: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None


@router.patch("/vehicles/{item_id}")
def update_vehicle(
    item_id: uuid.UUID, payload: VehiclePatch, db: Session = Depends(get_db), _=WriteDep
):
    """Ownership, the odometer and the LR counter are deliberately absent.

    `last_closing_km` is a chain of readings that runs across every freight the
    lorry has done, and `lr_next_number` is a consignment-note book. Typing
    either by hand breaks a control that exists to catch fraud. Odometer
    corrections go through the freight, where they are logged with a reason.
    """
    obj = _load(db, Vehicle, item_id, "Vehicle")
    data = payload.model_dump(exclude_unset=True)
    for key in ("vehicle_type_id", "owner_id"):
        if key in data:
            data[key] = uuid.UUID(data[key]) if data[key] else None
    if "registration_no" in data and data["registration_no"]:
        data["registration_no"] = "".join(data["registration_no"].split()).upper()
    for field, value in data.items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "registration_no": obj.registration_no}


@router.delete("/vehicles/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_vehicle(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    """Retired, never deleted. Its odometer readings are part of the chain that
    proves the kilometres on invoices already sent."""
    _retire(db, Vehicle, item_id, "Vehicle")


class DriverPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=20)
    licence_no: str | None = Field(default=None, max_length=40)
    default_vehicle_id: str | None = None
    is_active: bool | None = None


@router.patch("/drivers/{item_id}")
def update_driver(
    item_id: uuid.UUID, payload: DriverPatch, db: Session = Depends(get_db), _=WriteDep
):
    obj = _load(db, Driver, item_id, "Driver")
    data = payload.model_dump(exclude_unset=True)
    if "default_vehicle_id" in data:
        data["default_vehicle_id"] = (
            uuid.UUID(data["default_vehicle_id"]) if data["default_vehicle_id"] else None
        )
    for field, value in data.items():
        setattr(obj, field, value)

    # The driver's login is a separate record — Driver carries a user_id but no
    # relationship, so it is fetched rather than traversed. Keeping the phone in
    # step matters because the phone number IS the username: correcting it here
    # and not there locks him out with nobody realising why.
    if payload.phone and obj.user_id:
        login = db.get(User, obj.user_id)
        if login is not None and login.phone != payload.phone:
            # The phone is the username, so it is unique across every login.
            # Without this check the collision surfaces as a 500 from the
            # database and the admin is told nothing useful.
            taken = db.execute(
                select(User).where(User.phone == payload.phone, User.id != login.id)
            ).scalar_one_or_none()
            if taken is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"{payload.phone} is already the login for {taken.full_name}. "
                        "A phone number can only belong to one person."
                    ),
                )
            login.phone = payload.phone

    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/drivers/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_driver(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    """Retiring a driver also disables his login, which is the thing someone
    actually means when they say a driver has left."""
    driver = _load(db, Driver, item_id, "Driver")
    driver.is_active = False
    if driver.user_id:
        login = db.get(User, driver.user_id)
        if login is not None:
            login.is_active = False
    db.commit()


class LabourPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=20)
    daily_rate: Decimal | None = Field(default=None, ge=0)
    per_trip_rate: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


@router.patch("/labour/{item_id}")
def update_labour(
    item_id: uuid.UUID, payload: LabourPatch, db: Session = Depends(get_db), _=OpsDep
):
    obj = _load(db, Labour, item_id, "Loading crew member")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/labour/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_labour(item_id: uuid.UUID, db: Session = Depends(get_db), _=OpsDep):
    _retire(db, Labour, item_id, "Loading crew member")


# --------------------------------------------------------------------------- #
# Rates — retire only                                                          #
# --------------------------------------------------------------------------- #


@router.delete("/rate-cards/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_rate_card(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    """Retire a rate card. There is deliberately no PATCH.

    A rate agreed in April must still price an April freight in December.
    Editing a card would silently reprice freights already invoiced against it,
    and the vendor's copy of that invoice would no longer reconcile with ours.

    To change a rate, create a NEW card with the date the new rate starts. The
    old one keeps pricing the period it covered. Retiring stops a card applying
    to future freights without touching anything it has already priced.
    """
    _retire(db, RateCard, item_id, "Rate card")


class UnloadingRatePatch(BaseModel):
    """Furniture article rates. Editable, unlike the freight rate card.

    These price the unloading of one article at the point. They are not snapped
    into an invoice line the way the freight card is, so correcting a typo in a
    chair's base rate is a correction rather than a rewrite of history.
    """

    item_name: str | None = Field(default=None, min_length=1, max_length=160)
    item_code: str | None = Field(default=None, max_length=48)
    base_rate: Decimal | None = Field(default=None, ge=0)
    per_floor_rate: Decimal | None = Field(default=None, ge=0)
    charge_floors_with_lift: bool | None = None
    max_chargeable_floors: int | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None


@router.patch("/unloading-rates/{item_id}")
def update_unloading_rate(
    item_id: uuid.UUID, payload: UnloadingRatePatch, db: Session = Depends(get_db), _=WriteDep
):
    obj = _load(db, UnloadingItemRate, item_id, "Unloading rate")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "item_name": obj.item_name}


@router.delete("/unloading-rates/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_unloading_rate(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    _retire(db, UnloadingItemRate, item_id, "Unloading rate")


# --------------------------------------------------------------------------- #
# What a record is holding on to                                              #
# --------------------------------------------------------------------------- #


class UsageOut(BaseModel):
    """Why a record cannot simply be removed.

    Shown before retiring, so the answer to "can I delete this customer" is a
    count rather than a shrug.
    """

    in_use: bool
    freights: int = 0
    points: int = 0
    consignments: int = 0
    legs: int = 0
    summary: str


@router.get("/consignees/{item_id}/usage", response_model=UsageOut)
def consignee_usage(item_id: uuid.UUID, db: Session = Depends(get_db), _=OpsDep):
    points = _in_use(db, FreightPoint.consignee_id, item_id)
    consignments = _in_use(db, Consignment.consignee_id, item_id)
    total = points + consignments
    return UsageOut(
        in_use=total > 0,
        points=points,
        consignments=consignments,
        summary=(
            f"On {points} delivery point(s) and {consignments} consignment(s). "
            "Retiring hides them from new trips and leaves that history intact."
            if total
            else "Not used on any trip yet."
        ),
    )


@router.get("/vehicles/{item_id}/usage", response_model=UsageOut)
def vehicle_usage(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    legs = _in_use(db, FreightLeg.vehicle_id, item_id)
    return UsageOut(
        in_use=legs > 0,
        legs=legs,
        summary=(
            f"Has run {legs} leg(s). Its odometer readings are part of the chain "
            "behind invoices already sent, so it is retired rather than deleted."
            if legs
            else "Has never run a freight."
        ),
    )


@router.get("/drivers/{item_id}/usage", response_model=UsageOut)
def driver_usage(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    legs = _in_use(db, FreightLeg.driver_id, item_id)
    return UsageOut(
        in_use=legs > 0,
        legs=legs,
        summary=(
            f"Has driven {legs} leg(s), which his settlements are built from."
            if legs
            else "Has not driven a freight yet."
        ),
    )


@router.get("/vendors/{item_id}/usage", response_model=UsageOut)
def vendor_usage(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    divisions = db.execute(
        select(VendorDivision.id).where(VendorDivision.vendor_id == item_id)
    ).scalars().all()
    freights = 0
    if divisions:
        freights = int(
            db.execute(
                select(func.count()).where(Freight.vendor_division_id.in_(divisions))
            ).scalar()
            or 0
        )
    return UsageOut(
        in_use=freights > 0,
        freights=freights,
        summary=(
            f"{freights} freight(s) have been run for this vendor. Retiring keeps "
            "every invoice and settlement answerable."
            if freights
            else "No freights run for this vendor yet."
        ),
    )
