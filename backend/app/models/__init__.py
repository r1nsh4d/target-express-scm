"""Import every model here so Alembic's autogenerate sees the full metadata."""

from app.db.base import Base
from app.models.audit import AuditLog, OdometerCorrection
from app.models.billing import VendorInvoice, VendorInvoiceLine
from app.models.consignee import Consignee
from app.models.consignment import Box, Consignment
from app.models.enquiry import Enquiry
from app.models.expense import TripExpense
from app.models.fleet import (
    Driver,
    DriverPayTerms,
    Labour,
    Vehicle,
    VehicleHireTerms,
    VehicleOwner,
    VehicleType,
)
from app.models.freight import Freight, FreightLeg, FreightPoint
from app.models.market_vehicle import MarketVehicle
from app.models.route_preset import RoutePreset, RoutePresetPoint
from app.models.rating import RateCard, UnloadingItemRate
from app.models.settlement import Advance, FreightPayout, Settlement
from app.models.tracking import LocationChangeRequest, TrackingSession, VehiclePing
from app.models.user import User
from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

__all__ = [
    "Base",
    "AuditLog",
    "OdometerCorrection",
    "VendorInvoice",
    "VendorInvoiceLine",
    "Consignee",
    "Box",
    "Consignment",
    "Enquiry",
    "TripExpense",
    "Driver",
    "DriverPayTerms",
    "Labour",
    "Vehicle",
    "VehicleHireTerms",
    "VehicleOwner",
    "VehicleType",
    "Freight",
    "FreightLeg",
    "FreightPoint",
    "MarketVehicle",
    "RoutePreset",
    "RoutePresetPoint",
    "RateCard",
    "UnloadingItemRate",
    "Advance",
    "FreightPayout",
    "Settlement",
    "LocationChangeRequest",
    "TrackingSession",
    "VehiclePing",
    "User",
    "GoodsCategory",
    "Vendor",
    "VendorDivision",
    "VendorWarehouse",
]
