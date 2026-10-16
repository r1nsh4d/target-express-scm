"""How much is inside each tile.

A menu item says what a screen is called. A tile can say what is in it —
eleven vehicles, four enquiries nobody has rung — and that is the difference
between a list somebody reads and a list somebody scans.

One request rather than fourteen, because the hub draws all its tiles at once
and a screen that fires a query per tile is a screen that loads in pieces on
the connection this runs over.

Counts only, and cheap ones. Nothing here is a figure anybody acts on — it is
a number on a tile, and the screen behind it is the authority.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import BACK_OFFICE_ROLES, require_roles
from app.db.session import get_db
from app.models.billing import VendorInvoice
from app.models.consignee import Consignee
from app.models.consignment import Box, Consignment
from app.models.enquiry import Enquiry
from app.models.enums import (
    ApprovalStatus,
    EnquiryStatus,
    FreightStatus,
    InvoiceStatus,
)
from app.models.expense import TripExpense
from app.models.fleet import Driver, Labour, Vehicle
from app.models.freight import Freight
from app.models.market_vehicle import MarketVehicle
from app.models.rating import RateCard, UnloadingItemRate
from app.models.role import Role
from app.models.route_preset import RoutePreset
from app.models.settlement import Advance
from app.models.user import User
from app.models.vendor import Vendor

router = APIRouter(prefix="/api", tags=["hub"])


@router.get("/hub-counts", response_model=dict)
def hub_counts(db: Session = Depends(get_db), _=Depends(require_roles(*BACK_OFFICE_ROLES))):
    def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model)
        for clause in where:
            stmt = stmt.where(clause)
        return int(db.scalar(stmt) or 0)

    return {
        # Freights
        "freights_active": count(
            Freight,
            Freight.status.in_(
                [
                    FreightStatus.PLANNED,
                    FreightStatus.LOADING,
                    FreightStatus.DISPATCHED,
                    FreightStatus.IN_TRANSIT,
                ]
            ),
        ),
        "consignments": count(Consignment),
        # The one worth seeing from outside: a bill with no lorry cannot be
        # labelled or delivered, and nothing else on the screen says so.
        "consignments_waiting": count(Consignment, Consignment.freight_point_id.is_(None)),
        "returns": count(Box, Box.returned_at.isnot(None)),
        "presets": count(RoutePreset, RoutePreset.is_active.is_(True)),
        # Vendors
        "vendors": count(Vendor, Vendor.is_active.is_(True)),
        "consignees": count(Consignee, Consignee.is_active.is_(True)),
        "rate_cards": count(RateCard, RateCard.is_active.is_(True)),
        "unloading_rates": count(UnloadingItemRate, UnloadingItemRate.is_active.is_(True)),
        # Fleet
        "vehicles": count(Vehicle, Vehicle.is_active.is_(True)),
        "market_vehicles": count(MarketVehicle, MarketVehicle.is_active.is_(True)),
        "drivers": count(Driver, Driver.is_active.is_(True)),
        "labour": count(Labour, Labour.is_active.is_(True)),
        # Money
        "invoices": count(VendorInvoice),
        "invoices_unpaid": count(
            VendorInvoice,
            VendorInvoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.SENT]),
        ),
        "advances": count(Advance),
        # Pending, not all: an expense already decided is not waiting on
        # anybody, and a tile showing every expense ever would never change.
        "expenses_pending": count(
            TripExpense, TripExpense.approval_status == ApprovalStatus.PENDING
        ),
        # People
        "users": count(User, User.is_active.is_(True)),
        "roles": count(Role, Role.is_active.is_(True)),
        "enquiries": count(
            Enquiry, Enquiry.status == EnquiryStatus.NEW, Enquiry.is_spam.is_(False)
        ),
    }
