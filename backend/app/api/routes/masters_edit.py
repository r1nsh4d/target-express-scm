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
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_ROLES, WAREHOUSE_ROLES, require_capability, require_roles
from app.core.privileges import Capability
from app.db.session import get_db
from app.models.billing import VendorInvoiceLine
from app.models.consignee import Consignee
from app.models.consignment import Consignment
from app.models.enums import DriverEngagement, GeoConfidence
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

# The commercial terms: vendors, divisions, warehouses, categories, rates.
WriteDep = Depends(require_roles(*ADMIN_ROLES))
OpsDep = Depends(require_roles(*WAREHOUSE_ROLES))
# Customers, drivers, vehicles and crew — the warehouse's own list.
FleetDep = Depends(require_capability(Capability.FLEET))


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
    contact_person: str | None = Field(default=None, max_length=160)
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
    item_id: uuid.UUID, payload: ConsigneePatch, db: Session = Depends(get_db), _=FleetDep
):
    """Correcting a customer fixes them for every FUTURE delivery.

    Freights already built hold a snapshot of the address they were dispatched
    against, so this cannot rewrite what a past run was told to do.
    """
    obj = _load(db, Consignee, item_id, "Customer")
    _apply(obj, payload)

    # A pin dropped here is a good guess, not a confirmation.
    #
    # Without this the confidence never moved off UNVERIFIED, so a customer
    # could carry an exact pin while every screen described them as having
    # none — and the driver's app treats UNVERIFIED as "go and ask".
    #
    # APPROXIMATE rather than VERIFIED, deliberately. Somebody in the office
    # placing a marker from a town name is doing something genuinely weaker
    # than the customer standing at their own door, and collapsing the two
    # would throw away the only signal that says which is which.
    if payload.latitude is not None and payload.longitude is not None:
        if obj.geo_confidence != GeoConfidence.VERIFIED:
            obj.geo_confidence = GeoConfidence.APPROXIMATE

    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/consignees/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_consignee(item_id: uuid.UUID, db: Session = Depends(get_db), _=FleetDep):
    _retire(db, Consignee, item_id, "Customer")


@router.post("/consignees/{item_id}/restore")
def restore_consignee(item_id: uuid.UUID, db: Session = Depends(get_db), _=FleetDep):
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
    item_id: uuid.UUID, payload: VehicleTypePatch, db: Session = Depends(get_db), _=FleetDep
):
    obj = _load(db, VehicleType, item_id, "Vehicle type")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/vehicle-types/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_vehicle_type(item_id: uuid.UUID, db: Session = Depends(get_db), _=FleetDep):
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
    item_id: uuid.UUID, payload: VehicleOwnerPatch, db: Session = Depends(get_db), _=FleetDep
):
    obj = _load(db, VehicleOwner, item_id, "Vehicle owner")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/vehicle-owners/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_vehicle_owner(item_id: uuid.UUID, db: Session = Depends(get_db), _=FleetDep):
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
    item_id: uuid.UUID, payload: VehiclePatch, db: Session = Depends(get_db), _=FleetDep
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
def retire_vehicle(item_id: uuid.UUID, db: Session = Depends(get_db), _=FleetDep):
    """Retired, never deleted. Its odometer readings are part of the chain that
    proves the kilometres on invoices already sent."""
    _retire(db, Vehicle, item_id, "Vehicle")


class DriverPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=20)
    licence_no: str | None = Field(default=None, max_length=40)
    default_vehicle_id: str | None = None
    # Whose man he is. Sent as null to make him ours again, which is why it
    # is paired with a flag rather than relying on "omitted means unchanged"
    # — null is a real answer here.
    vehicle_owner_id: str | None = None
    set_owner: bool = False
    is_active: bool | None = None


@router.patch("/drivers/{item_id}")
def update_driver(
    item_id: uuid.UUID, payload: DriverPatch, db: Session = Depends(get_db), _=FleetDep
):
    obj = _load(db, Driver, item_id, "Driver")
    data = payload.model_dump(exclude_unset=True)

    # Moving a man between Target Express and an owner, or the other way.
    set_owner = data.pop("set_owner", False)
    owner_id = data.pop("vehicle_owner_id", None)
    if set_owner:
        if owner_id is not None and db.get(VehicleOwner, owner_id) is None:
            raise HTTPException(status_code=404, detail="Vehicle owner not found")
        obj.vehicle_owner_id = uuid.UUID(owner_id) if owner_id else None
        # Kept in step, so the badge on his tile and the record agree.
        obj.engagement = (
            DriverEngagement.ATTACHED_TO_HIRED_VEHICLE
            if owner_id
            else DriverEngagement.OWN_STAFF
        )

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
def retire_driver(item_id: uuid.UUID, db: Session = Depends(get_db), _=FleetDep):
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
    item_id: uuid.UUID, payload: LabourPatch, db: Session = Depends(get_db), _=FleetDep
):
    obj = _load(db, Labour, item_id, "Loading crew member")
    _apply(obj, payload)
    db.commit()
    db.refresh(obj)
    return {"id": str(obj.id), "name": obj.name}


@router.delete("/labour/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_labour(item_id: uuid.UUID, db: Session = Depends(get_db), _=FleetDep):
    _retire(db, Labour, item_id, "Loading crew member")


# --------------------------------------------------------------------------- #
# Rates                                                                        #
# --------------------------------------------------------------------------- #


def _rate_card_is_locked(db: Session, card_id: uuid.UUID) -> int:
    """How many issued invoices this card has priced.

    Nonzero means it is locked. The test is deliberately "has it priced an
    invoice", not "has any freight used it": a dispatched freight carries a
    frozen copy of the card's numbers in `rate_snapshot`, so correcting the
    card cannot move a price that has already been struck. What it must never
    do is move a price the vendor has already been sent.
    """
    return int(
        db.scalar(
            select(func.count())
            .select_from(VendorInvoiceLine)
            .join(Freight, Freight.id == VendorInvoiceLine.freight_id)
            .where(Freight.rate_card_id == card_id)
        )
        or 0
    )


class RateCardPatch(BaseModel):
    """Correcting a card, not changing a rate.

    These are two different things and the endpoint treats them differently.

    A TYPO is a correction. Somebody has just entered Godrej OCP at 1,687
    instead of 1,867 and no invoice has gone out on it. Making them retire the
    card and re-key eleven fields to fix one transposed digit is how a master
    list stops being trusted — and the old behaviour, which was to offer no
    edit at all, is exactly that.

    A RATE CHANGE is a new agreement, and it is still a new card dated from the
    day it starts. A card that has already priced an invoice is refused here,
    with the reason, because editing it would reprice work the vendor has
    already been sent a bill for and the two copies would stop reconciling.

    So: freely editable until it has billed something, then frozen. The screen
    shows which state a card is in rather than letting somebody find out from
    an error.
    """

    vehicle_type_id: uuid.UUID | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    base_trip_amount: Decimal | None = Field(default=None, ge=0)
    included_km: int | None = Field(default=None, ge=0)
    extra_km_rate: Decimal | None = Field(default=None, ge=0)
    base_point_charge: Decimal | None = Field(default=None, ge=0)
    included_points: int | None = Field(default=None, ge=0)
    extra_point_rate: Decimal | None = Field(default=None, ge=0)
    unloading_basis: str | None = Field(default=None, max_length=32)
    unloading_rate: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


@router.patch("/rate-cards/{item_id}")
def update_rate_card(
    item_id: uuid.UUID, payload: RateCardPatch, db: Session = Depends(get_db), _=WriteDep
):
    card = _load(db, RateCard, item_id, "Rate card")

    invoiced = _rate_card_is_locked(db, card.id)
    if invoiced:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"This card has already priced {invoiced} invoiced "
                f"{'freight' if invoiced == 1 else 'freights'}. Editing it would reprice "
                "work the vendor has been billed for. Add a new card dated from the day "
                "the new rate starts instead — freights before that keep this one."
            ),
        )

    _apply(card, payload)
    db.commit()
    db.refresh(card)
    return {"id": str(card.id), "effective_from": card.effective_from.isoformat()}


@router.get("/rate-cards/{item_id}/usage")
def rate_card_usage(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    """Whether this card can still be corrected, and why not if it cannot.

    The screen asks before showing an edit button, so somebody is told the
    card is frozen before they have filled in a form, not after.
    """
    card = _load(db, RateCard, item_id, "Rate card")
    invoiced = _rate_card_is_locked(db, card.id)
    freights = int(
        db.scalar(
            select(func.count()).select_from(Freight).where(Freight.rate_card_id == card.id)
        )
        or 0
    )
    return {"invoiced_freights": invoiced, "freights": freights, "editable": invoiced == 0}


@router.delete("/rate-cards/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def retire_rate_card(item_id: uuid.UUID, db: Session = Depends(get_db), _=WriteDep):
    """Retire a rate card.

    A rate agreed in April must still price an April freight in December.
    Retiring stops a card applying to future freights without touching
    anything it has already priced.
    """
    _retire(db, RateCard, item_id, "Rate card")


class UnloadingRatePatch(BaseModel):
    """Furniture article rates. Editable, unlike a rate card that has billed.

    These price the unloading of one article at the point. They are not snapped
    into an invoice line the way the freight card is, so correcting a typo in a
    chair's base rate is a correction rather than a rewrite of history.
    """

    item_name: str | None = Field(default=None, min_length=1, max_length=160)
    item_code: str | None = Field(default=None, max_length=48)
    base_rate: Decimal | None = Field(default=None, ge=0)
    per_floor_rate: Decimal | None = Field(default=None, ge=0)
    # The driver's side of the same article. Missing here until now, which
    # meant the edit form could show the figure and silently fail to save it.
    driver_base_rate: Decimal | None = Field(default=None, ge=0)
    driver_per_floor_rate: Decimal | None = Field(default=None, ge=0)
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
def consignee_usage(item_id: uuid.UUID, db: Session = Depends(get_db), _=FleetDep):
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
def vehicle_usage(item_id: uuid.UUID, db: Session = Depends(get_db), _=FleetDep):
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
def driver_usage(item_id: uuid.UUID, db: Session = Depends(get_db), _=FleetDep):
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
