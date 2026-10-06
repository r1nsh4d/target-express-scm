"""Response models must accept what the ORM actually returns.

Postgres UUID columns come back as `uuid.UUID`. Pydantic v2 does not coerce
that into a declared `str`, so every masters endpoint returned a 500 until the
response models inherited ORMModel. These tests pin that down: they construct
ORM objects exactly as SQLAlchemy hands them over, with real UUIDs.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.api.routes.masters import (
    ConsigneeOut,
    DriverOut,
    RateCardOut,
    VehicleOut,
    VehicleTypeOut,
    VendorDivisionOut,
    VendorOut,
    WarehouseOut,
)
from app.models.consignee import Consignee
from app.models.enums import (
    ConsigneeType,
    DriverEngagement,
    GeoConfidence,
    UnloadingBasis,
    VehicleOwnership,
)
from app.models.fleet import Driver, Vehicle, VehicleType
from app.models.rating import RateCard
from app.models.vendor import Vendor, VendorDivision, VendorWarehouse


def test_vendor_with_a_real_uuid_serialises():
    vendor = Vendor(id=uuid.uuid4(), name="Godrej", payment_terms_days=30, is_active=True)
    out = VendorOut.model_validate(vendor)

    assert isinstance(out.id, str)
    assert out.id == str(vendor.id)
    assert out.name == "Godrej"


def test_foreign_keys_are_stringified_too():
    """Not just `id` - every UUID column on the row."""
    division = VendorDivision(
        id=uuid.uuid4(),
        vendor_id=uuid.uuid4(),
        goods_category_id=uuid.uuid4(),
        name="Godrej Appliance Spare",
        code="GODREJ-APPLIANCE-SPARE",
        invoice_series="191",
        gst_rate_percent=Decimal("12"),
        is_active=True,
    )
    out = VendorDivisionOut.model_validate(division)

    assert isinstance(out.id, str)
    assert isinstance(out.vendor_id, str)
    assert isinstance(out.goods_category_id, str)


def test_a_null_foreign_key_stays_none():
    division = VendorDivision(
        id=uuid.uuid4(),
        vendor_id=uuid.uuid4(),
        goods_category_id=None,
        name="Godrej OCP",
        code="GODREJ-OCP",
        invoice_series="191",
        gst_rate_percent=Decimal("12"),
        is_active=True,
    )
    assert VendorDivisionOut.model_validate(division).goods_category_id is None


def test_vehicle_type_serialises():
    vtype = VehicleType(id=uuid.uuid4(), name="DOST", capacity_kg=1250, is_active=True)
    out = VehicleTypeOut.model_validate(vtype)

    assert isinstance(out.id, str)
    assert out.name == "DOST"


def test_vehicle_serialises_with_optional_owner():
    vehicle = Vehicle(
        id=uuid.uuid4(),
        registration_no="KL07AA1234",
        vehicle_type_id=uuid.uuid4(),
        ownership=VehicleOwnership.OWNED,
        owner_id=None,
        lr_prefix="",
        lr_next_number=1,
        last_closing_km=0,
        is_active=True,
    )
    out = VehicleOut.model_validate(vehicle)

    assert isinstance(out.id, str)
    assert isinstance(out.vehicle_type_id, str)
    assert out.owner_id is None


def test_driver_serialises():
    driver = Driver(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Rajesh K",
        phone="9000000010",
        # Set explicitly: SQLAlchemy column defaults are applied on insert, not
        # on construction, so an unflushed object would carry None here.
        engagement=DriverEngagement.OWN_STAFF,
        default_vehicle_id=uuid.uuid4(),
        is_active=True,
    )
    out = DriverOut.model_validate(driver)

    assert isinstance(out.id, str)
    assert isinstance(out.user_id, str)
    assert isinstance(out.default_vehicle_id, str)


def test_consignee_serialises():
    consignee = Consignee(
        id=uuid.uuid4(),
        name="Kannur Distribution Centre",
        type=ConsigneeType.DISTRIBUTION_CENTER,
        geo_confidence=GeoConfidence.APPROXIMATE,
        is_active=True,
    )
    out = ConsigneeOut.model_validate(consignee)

    assert isinstance(out.id, str)
    assert out.type == ConsigneeType.DISTRIBUTION_CENTER


def test_warehouse_serialises():
    warehouse = VendorWarehouse(
        id=uuid.uuid4(),
        vendor_id=uuid.uuid4(),
        name="Godrej Warehouse, Ernakulam",
        code="GODREJ-EKM",
        is_active=True,
    )
    out = WarehouseOut.model_validate(warehouse)

    assert isinstance(out.id, str)
    assert isinstance(out.vendor_id, str)


def test_rate_card_serialises_with_a_null_vehicle_type():
    card = RateCard(
        id=uuid.uuid4(),
        vendor_division_id=uuid.uuid4(),
        vehicle_type_id=None,
        effective_from=date(2026, 4, 1),
        base_trip_amount=Decimal("1867.00"),
        included_km=60,
        extra_km_rate=Decimal("17.00"),
        base_point_charge=Decimal("0"),
        included_points=3,
        extra_point_rate=Decimal("175.00"),
        unloading_basis=UnloadingBasis.NOT_APPLICABLE,
        unloading_rate=Decimal("0"),
        is_active=True,
    )
    out = RateCardOut.model_validate(card)

    assert isinstance(out.id, str)
    assert out.vehicle_type_id is None
    assert out.base_trip_amount == Decimal("1867.00")


@pytest.mark.parametrize(
    "model",
    [
        VendorOut,
        VendorDivisionOut,
        WarehouseOut,
        ConsigneeOut,
        VehicleTypeOut,
        VehicleOut,
        DriverOut,
        RateCardOut,
    ],
)
def test_every_response_model_reads_from_orm_objects(model):
    """A response model that forgets from_attributes fails at runtime, not at
    import, so it is worth asserting directly."""
    assert model.model_config.get("from_attributes") is True
