"""Master data: everything an admin sets up before a trip can exist.

Deliberately plain CRUD. The interesting rules live in the services; these
endpoints only have to be predictable.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_ROLES, BACK_OFFICE_ROLES, WAREHOUSE_ROLES, require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models.consignee import Consignee
from app.models.enums import (
    ConsigneeType,
    DriverEngagement,
    GeoConfidence,
    HireRateBasis,
    UnloadingBasis,
    UnloadingShareBasis,
    UserRole,
    VehicleOwnership,
)
from app.models.fleet import (
    Driver,
    DriverPayTerms,
    Labour,
    Vehicle,
    VehicleHireTerms,
    VehicleOwner,
    VehicleType,
)
from app.models.rating import RateCard, UnloadingItemRate
from app.models.user import User
from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse
from app.schemas.base import ORMModel

router = APIRouter(prefix="/api", tags=["masters"])

ReadDep = Depends(require_roles(*BACK_OFFICE_ROLES))
WriteDep = Depends(require_roles(*ADMIN_ROLES))
OpsDep = Depends(require_roles(*WAREHOUSE_ROLES))


def _get_or_404(db: Session, model, obj_id, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    return obj


def _save(db: Session, obj):
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# --------------------------------------------------------------------------- #
# Goods categories                                                            #
# --------------------------------------------------------------------------- #

class GoodsCategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=24)
    is_fragile: bool = False
    is_bulky: bool = False


class GoodsCategoryOut(GoodsCategoryIn, ORMModel):
    id: str
    is_active: bool


@router.get("/goods-categories", response_model=list[GoodsCategoryOut])
def list_goods_categories(
    include_inactive: bool = False, db: Session = Depends(get_db), _=ReadDep
):
    stmt = select(GoodsCategory).order_by(GoodsCategory.name)
    # Retired records drop out of the pickers but stay reachable with
    # include_inactive, because they are still attached to freights,
    # invoices and settlements that have to keep answering for themselves.
    if not include_inactive:
        stmt = stmt.where(GoodsCategory.is_active.is_(True))
    rows = db.execute(stmt).scalars().all()
    return [GoodsCategoryOut.model_validate(r) for r in rows]


@router.post("/goods-categories", response_model=GoodsCategoryOut, status_code=201)
def create_goods_category(payload: GoodsCategoryIn, db: Session = Depends(get_db), _=WriteDep):
    return GoodsCategoryOut.model_validate(
        _save(db, GoodsCategory(**payload.model_dump()))
    )


# --------------------------------------------------------------------------- #
# Vendors, divisions, warehouses                                              #
# --------------------------------------------------------------------------- #

class VendorIn(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    gstin: str | None = None
    pan: str | None = None
    billing_address: str | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    payment_terms_days: int = 30


class VendorOut(VendorIn, ORMModel):
    id: str
    is_active: bool


@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(
    include_inactive: bool = False, db: Session = Depends(get_db), _=ReadDep
):
    stmt = select(Vendor).order_by(Vendor.name)
    # Retired records drop out of the pickers but stay reachable with
    # include_inactive, because they are still attached to freights,
    # invoices and settlements that have to keep answering for themselves.
    if not include_inactive:
        stmt = stmt.where(Vendor.is_active.is_(True))
    rows = db.execute(stmt).scalars().all()
    return [VendorOut.model_validate(r) for r in rows]


@router.post("/vendors", response_model=VendorOut, status_code=201)
def create_vendor(payload: VendorIn, db: Session = Depends(get_db), _=WriteDep):
    if db.execute(select(Vendor).where(Vendor.name == payload.name)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A vendor with this name already exists")
    return VendorOut.model_validate(_save(db, Vendor(**payload.model_dump())))


class VendorDivisionIn(BaseModel):
    vendor_id: str
    name: str = Field(min_length=2, max_length=180)
    code: str = Field(min_length=2, max_length=32)
    goods_category_id: str | None = None
    gstin: str | None = None
    billing_address: str | None = None
    invoice_series: str = "191"
    place_of_supply_state_code: str | None = None
    gst_rate_percent: Decimal = Decimal("12")


class VendorDivisionOut(VendorDivisionIn, ORMModel):
    id: str
    is_active: bool
    vendor_name: str | None = None


@router.get("/vendor-divisions", response_model=list[VendorDivisionOut])
def list_vendor_divisions(
    vendor_id: str | None = None, db: Session = Depends(get_db), _=ReadDep
):
    stmt = select(VendorDivision).order_by(VendorDivision.name)
    if vendor_id:
        stmt = stmt.where(VendorDivision.vendor_id == vendor_id)
    rows = db.execute(stmt).scalars().all()
    out = []
    for r in rows:
        item = VendorDivisionOut.model_validate(r)
        item.vendor_name = r.vendor.name if r.vendor else None
        out.append(item)
    return out


@router.post("/vendor-divisions", response_model=VendorDivisionOut, status_code=201)
def create_vendor_division(
    payload: VendorDivisionIn, db: Session = Depends(get_db), _=WriteDep
):
    _get_or_404(db, Vendor, payload.vendor_id, "Vendor")
    return VendorDivisionOut.model_validate(_save(db, VendorDivision(**payload.model_dump())))


class WarehouseIn(BaseModel):
    vendor_id: str
    name: str = Field(min_length=2, max_length=180)
    code: str = Field(min_length=2, max_length=32)
    address: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    contact_phone: str | None = None


class WarehouseOut(WarehouseIn, ORMModel):
    id: str
    is_active: bool


@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(vendor_id: str | None = None, db: Session = Depends(get_db), _=ReadDep):
    stmt = select(VendorWarehouse).order_by(VendorWarehouse.name)
    if vendor_id:
        stmt = stmt.where(VendorWarehouse.vendor_id == vendor_id)
    return [WarehouseOut.model_validate(r) for r in db.execute(stmt).scalars().all()]


@router.post("/warehouses", response_model=WarehouseOut, status_code=201)
def create_warehouse(payload: WarehouseIn, db: Session = Depends(get_db), _=WriteDep):
    _get_or_404(db, Vendor, payload.vendor_id, "Vendor")
    return WarehouseOut.model_validate(_save(db, VendorWarehouse(**payload.model_dump())))


# --------------------------------------------------------------------------- #
# Consignees                                                                  #
# --------------------------------------------------------------------------- #

class ConsigneeIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    type: ConsigneeType = ConsigneeType.RETAIL_CUSTOMER
    phone: str | None = None
    alternate_phone: str | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = "Kerala"
    pincode: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    landmark: str | None = None
    delivery_notes: str | None = None


class ConsigneeOut(ConsigneeIn, ORMModel):
    id: str
    geo_confidence: GeoConfidence
    is_active: bool


@router.get("/consignees", response_model=list[ConsigneeOut])
def list_consignees(
    q: str | None = Query(default=None, description="Match on name, city or phone"),
    include_inactive: bool = False,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _=ReadDep,
):
    stmt = select(Consignee).order_by(Consignee.name).limit(limit)
    # Retired records drop out of the pickers but stay reachable with
    # include_inactive, because they are still attached to freights,
    # invoices and settlements that have to keep answering for themselves.
    if not include_inactive:
        stmt = stmt.where(Consignee.is_active.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Consignee.name.ilike(like), Consignee.city.ilike(like), Consignee.phone.ilike(like))
        )
    return [ConsigneeOut.model_validate(r) for r in db.execute(stmt).scalars().all()]


@router.post("/consignees", response_model=ConsigneeOut, status_code=201)
def create_consignee(payload: ConsigneeIn, db: Session = Depends(get_db), _=OpsDep):
    data = payload.model_dump()
    # A pin typed in by an admin is better than nothing but has not been
    # confirmed on the ground; the customer's own correction upgrades it.
    if data.get("latitude") is not None:
        data["geo_confidence"] = GeoConfidence.APPROXIMATE
    return ConsigneeOut.model_validate(_save(db, Consignee(**data)))


# --------------------------------------------------------------------------- #
# Fleet                                                                       #
# --------------------------------------------------------------------------- #

class VehicleTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    capacity_kg: int | None = None
    capacity_cbm: Decimal | None = None


class VehicleTypeOut(VehicleTypeIn, ORMModel):
    id: str
    is_active: bool


@router.get("/vehicle-types", response_model=list[VehicleTypeOut])
def list_vehicle_types(
    include_inactive: bool = False, db: Session = Depends(get_db), _=ReadDep
):
    stmt = select(VehicleType).order_by(VehicleType.name)
    # Retired records drop out of the pickers but stay reachable with
    # include_inactive, because they are still attached to freights,
    # invoices and settlements that have to keep answering for themselves.
    if not include_inactive:
        stmt = stmt.where(VehicleType.is_active.is_(True))
    rows = db.execute(stmt).scalars().all()
    return [VehicleTypeOut.model_validate(r) for r in rows]


@router.post("/vehicle-types", response_model=VehicleTypeOut, status_code=201)
def create_vehicle_type(payload: VehicleTypeIn, db: Session = Depends(get_db), _=WriteDep):
    return VehicleTypeOut.model_validate(_save(db, VehicleType(**payload.model_dump())))


class VehicleOwnerIn(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    phone: str = Field(min_length=6, max_length=20)
    address: str | None = None
    pan: str | None = None
    gstin: str | None = None
    bank_account: str | None = None
    ifsc: str | None = None
    bank_name: str | None = None


class VehicleOwnerOut(VehicleOwnerIn, ORMModel):
    id: str
    is_active: bool


@router.get("/vehicle-owners", response_model=list[VehicleOwnerOut])
def list_vehicle_owners(
    include_inactive: bool = False, db: Session = Depends(get_db), _=ReadDep
):
    stmt = select(VehicleOwner).order_by(VehicleOwner.name)
    # Retired records drop out of the pickers but stay reachable with
    # include_inactive, because they are still attached to freights,
    # invoices and settlements that have to keep answering for themselves.
    if not include_inactive:
        stmt = stmt.where(VehicleOwner.is_active.is_(True))
    rows = db.execute(stmt).scalars().all()
    return [VehicleOwnerOut.model_validate(r) for r in rows]


@router.post("/vehicle-owners", response_model=VehicleOwnerOut, status_code=201)
def create_vehicle_owner(payload: VehicleOwnerIn, db: Session = Depends(get_db), _=WriteDep):
    return VehicleOwnerOut.model_validate(_save(db, VehicleOwner(**payload.model_dump())))


class VehicleIn(BaseModel):
    registration_no: str = Field(min_length=4, max_length=24)
    vehicle_type_id: str | None = None
    ownership: VehicleOwnership = VehicleOwnership.OWNED
    owner_id: str | None = None
    lr_prefix: str = ""
    lr_next_number: int = 1
    last_closing_km: int | None = None
    insurance_expiry: date | None = None
    fitness_expiry: date | None = None
    permit_expiry: date | None = None
    notes: str | None = None

    # Optional hire terms, created alongside a rented vehicle.
    hire_rate_basis: HireRateBasis | None = None
    hire_rate_value: Decimal | None = None
    hire_minimum_km: int = 0
    hire_includes_unloading: bool = False


class VehicleOut(ORMModel):
    id: str
    registration_no: str
    vehicle_type_id: str | None
    vehicle_type_name: str | None = None
    ownership: VehicleOwnership
    owner_id: str | None
    owner_name: str | None = None
    lr_prefix: str
    lr_next_number: int
    last_closing_km: int | None
    is_active: bool


def _vehicle_out(v: Vehicle) -> VehicleOut:
    out = VehicleOut.model_validate(v)
    out.vehicle_type_name = v.vehicle_type.name if v.vehicle_type else None
    out.owner_name = v.owner.name if v.owner else None
    return out


@router.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles(
    include_inactive: bool = False, db: Session = Depends(get_db), _=ReadDep
):
    stmt = select(Vehicle).order_by(Vehicle.registration_no)
    # Retired records drop out of the pickers but stay reachable with
    # include_inactive, because they are still attached to freights,
    # invoices and settlements that have to keep answering for themselves.
    if not include_inactive:
        stmt = stmt.where(Vehicle.is_active.is_(True))
    rows = db.execute(stmt).scalars().all()
    return [_vehicle_out(v) for v in rows]


@router.post("/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(payload: VehicleIn, db: Session = Depends(get_db), _=WriteDep):
    existing = db.execute(
        select(Vehicle).where(Vehicle.registration_no == payload.registration_no)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="This registration already exists")

    if payload.ownership == VehicleOwnership.HIRED and not payload.owner_id:
        raise HTTPException(
            status_code=400,
            detail="A rented vehicle needs an owner - that is who gets paid for its trips",
        )

    data = payload.model_dump(
        exclude={
            "hire_rate_basis",
            "hire_rate_value",
            "hire_minimum_km",
            "hire_includes_unloading",
        }
    )
    vehicle = Vehicle(**data)
    db.add(vehicle)
    db.flush()

    if payload.hire_rate_basis and payload.hire_rate_value is not None:
        db.add(
            VehicleHireTerms(
                vehicle_id=vehicle.id,
                rate_basis=payload.hire_rate_basis,
                rate_value=payload.hire_rate_value,
                minimum_km_per_trip=payload.hire_minimum_km,
                includes_unloading=payload.hire_includes_unloading,
                effective_from=date.today(),
            )
        )

    db.commit()
    db.refresh(vehicle)
    return _vehicle_out(vehicle)


class DriverIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=6, max_length=20)
    engagement: DriverEngagement = DriverEngagement.OWN_STAFF
    licence_no: str | None = None
    licence_expiry: date | None = None
    address: str | None = None
    default_vehicle_id: str | None = None

    # Pay terms. Target Express pays on distance plus the unloading cash.
    per_km_amount: Decimal = Decimal("0")
    unloading_share_percent: Decimal = Decimal("100")
    # A share of WHICH pot. Defaults to what was paid out, because the billed
    # amount is zero on spare-parts runs while cash still leaves the driver's
    # pocket - defaulting to the billed basis would quietly stop paying him.
    unloading_share_basis: UnloadingShareBasis = UnloadingShareBasis.PAID_AT_POINT
    per_trip_amount: Decimal = Decimal("0")
    per_point_amount: Decimal = Decimal("0")
    daily_allowance: Decimal = Decimal("0")

    # Create a login for him at the same time.
    create_login: bool = True
    password: str | None = None
    can_view_earnings: bool = True


class DriverOut(ORMModel):
    id: str
    name: str
    phone: str
    engagement: DriverEngagement
    licence_no: str | None
    default_vehicle_id: str | None
    user_id: str | None
    is_active: bool


@router.get("/drivers", response_model=list[DriverOut])
def list_drivers(
    include_inactive: bool = False, db: Session = Depends(get_db), _=ReadDep
):
    stmt = select(Driver).order_by(Driver.name)
    # Retired records drop out of the pickers but stay reachable with
    # include_inactive, because they are still attached to freights,
    # invoices and settlements that have to keep answering for themselves.
    if not include_inactive:
        stmt = stmt.where(Driver.is_active.is_(True))
    rows = db.execute(stmt).scalars().all()
    return [DriverOut.model_validate(r) for r in rows]


@router.post("/drivers", response_model=DriverOut, status_code=201)
def create_driver(payload: DriverIn, db: Session = Depends(get_db), _=WriteDep):
    if db.execute(select(Driver).where(Driver.phone == payload.phone)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A driver with this phone already exists")

    user_id = None
    if payload.create_login:
        existing = db.execute(
            select(User).where(User.phone == payload.phone)
        ).scalar_one_or_none()
        if existing:
            user_id = existing.id
        else:
            user = User(
                full_name=payload.name,
                phone=payload.phone,
                role=UserRole.DRIVER,
                can_view_earnings=payload.can_view_earnings,
                hashed_password=hash_password(payload.password or payload.phone[-6:]),
            )
            db.add(user)
            db.flush()
            user_id = user.id

    driver = Driver(
        name=payload.name,
        phone=payload.phone,
        engagement=payload.engagement,
        licence_no=payload.licence_no,
        licence_expiry=payload.licence_expiry,
        address=payload.address,
        default_vehicle_id=payload.default_vehicle_id,
        user_id=user_id,
    )
    db.add(driver)
    db.flush()

    db.add(
        DriverPayTerms(
            driver_id=driver.id,
            per_km_amount=payload.per_km_amount,
            unloading_share_percent=payload.unloading_share_percent,
            unloading_share_basis=payload.unloading_share_basis,
            per_trip_amount=payload.per_trip_amount,
            per_point_amount=payload.per_point_amount,
            daily_allowance=payload.daily_allowance,
            effective_from=date.today(),
        )
    )

    db.commit()
    db.refresh(driver)
    return DriverOut.model_validate(driver)


class LabourIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    phone: str | None = None
    warehouse_id: str | None = None
    daily_rate: Decimal = Decimal("0")
    per_trip_rate: Decimal = Decimal("0")


class LabourOut(LabourIn, ORMModel):
    id: str
    is_active: bool


@router.get("/labour", response_model=list[LabourOut])
def list_labour(
    include_inactive: bool = False, db: Session = Depends(get_db), _=ReadDep
):
    stmt = select(Labour).order_by(Labour.name)
    # Retired records drop out of the pickers but stay reachable with
    # include_inactive, because they are still attached to freights,
    # invoices and settlements that have to keep answering for themselves.
    if not include_inactive:
        stmt = stmt.where(Labour.is_active.is_(True))
    return [LabourOut.model_validate(r) for r in db.execute(stmt).scalars().all()]


@router.post("/labour", response_model=LabourOut, status_code=201)
def create_labour(payload: LabourIn, db: Session = Depends(get_db), _=OpsDep):
    return LabourOut.model_validate(_save(db, Labour(**payload.model_dump())))


# --------------------------------------------------------------------------- #
# Rate cards                                                                  #
# --------------------------------------------------------------------------- #

class RateCardIn(BaseModel):
    vendor_division_id: str
    vehicle_type_id: str | None = None
    effective_from: date
    effective_to: date | None = None
    base_trip_amount: Decimal
    included_km: int = 0
    extra_km_rate: Decimal = Decimal("0")
    base_point_charge: Decimal = Decimal("0")
    included_points: int = 0
    extra_point_rate: Decimal = Decimal("0")
    unloading_basis: UnloadingBasis = UnloadingBasis.NOT_APPLICABLE
    unloading_rate: Decimal = Decimal("0")
    notes: str | None = None


class RateCardOut(RateCardIn, ORMModel):
    id: str
    is_active: bool


@router.get("/rate-cards", response_model=list[RateCardOut])
def list_rate_cards(
    vendor_division_id: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _=ReadDep,
):
    stmt = select(RateCard).order_by(RateCard.effective_from.desc())
    # A retired card stops applying to NEW freights. It is never removed: it is
    # still the card that priced every invoice issued while it was in force, and
    # a vendor query six months from now has to be able to find it.
    if not include_inactive:
        stmt = stmt.where(RateCard.is_active.is_(True))
    if vendor_division_id:
        stmt = stmt.where(RateCard.vendor_division_id == vendor_division_id)
    return [RateCardOut.model_validate(r) for r in db.execute(stmt).scalars().all()]


@router.post("/rate-cards", response_model=RateCardOut, status_code=201)
def create_rate_card(payload: RateCardIn, db: Session = Depends(get_db), _=WriteDep):
    """Rates are never edited in place.

    To change a rate, add a card dated from the change. Trips before it keep
    pricing on the old card, which is what lets an old invoice re-print
    unchanged.
    """
    _get_or_404(db, VendorDivision, payload.vendor_division_id, "Vendor division")
    return RateCardOut.model_validate(_save(db, RateCard(**payload.model_dump())))


class UnloadingItemRateIn(BaseModel):
    vendor_division_id: str
    item_code: str = Field(min_length=1, max_length=48)
    item_name: str = Field(min_length=1, max_length=160)
    base_rate: Decimal
    per_floor_rate: Decimal = Decimal("0")
    charge_floors_with_lift: bool = False
    max_chargeable_floors: int = 0
    effective_from: date
    effective_to: date | None = None


class UnloadingItemRateOut(UnloadingItemRateIn, ORMModel):
    id: str
    is_active: bool


@router.get("/unloading-rates", response_model=list[UnloadingItemRateOut])
def list_unloading_rates(
    vendor_division_id: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _=ReadDep,
):
    stmt = select(UnloadingItemRate).order_by(UnloadingItemRate.item_name)
    if not include_inactive:
        stmt = stmt.where(UnloadingItemRate.is_active.is_(True))
    if vendor_division_id:
        stmt = stmt.where(UnloadingItemRate.vendor_division_id == vendor_division_id)
    return [UnloadingItemRateOut.model_validate(r) for r in db.execute(stmt).scalars().all()]


@router.post("/unloading-rates", response_model=UnloadingItemRateOut, status_code=201)
def create_unloading_rate(
    payload: UnloadingItemRateIn, db: Session = Depends(get_db), _=WriteDep
):
    _get_or_404(db, VendorDivision, payload.vendor_division_id, "Vendor division")
    return UnloadingItemRateOut.model_validate(_save(db, UnloadingItemRate(**payload.model_dump())))
