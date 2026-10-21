"""The vendor's own view of the work Target Express does for them.

Godrej's people want four things and have been getting them by telephone: put
tomorrow's run in, check what was agreed, see what happened at each door, and
reconcile the bill. None of that needs a Target Express person in the middle,
and every one of those calls is somebody's morning.

ONE RULE, AND EVERYTHING HERE IS A CONSEQUENCE OF IT

A vendor login is tied to one vendor and every query filters on it. Godrej
must never see a line of Usha's — not a freight, not a rate, not an invoice,
not a customer. The filter is in the query rather than in what the screen
chooses to draw, because a screen that forgets is a leak and a query that
forgets returns nothing.

That is also why this is its own module rather than a flag on the office
routes. An office endpoint answers "all of it" and would have to remember to
narrow; these answer "mine" and have nothing else to return.

WHAT THEY CAN CHANGE, AND WHAT THEY CANNOT

They raise a freight, because they know what is going out tomorrow before we
do. It arrives as a DRAFT against their own division, and Target Express
assigns the lorry, prints the labels and dispatches it — those are ours, and a
vendor pressing dispatch would be a vendor telling us a lorry has left.

They read the rate card and cannot touch it. A rate is an agreement between
two companies; one of them editing it alone is not a rate change, it is a
dispute waiting to be discovered at invoice time.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_capability
from app.core.privileges import Capability
from app.db.session import get_db
from app.models.billing import VendorInvoice
from app.models.consignee import Consignee
from app.models.consignment import Consignment
from app.models.enums import FreightStatus, InvoiceStatus
from app.models.freight import Freight, FreightPoint
from app.models.rating import RateCard, UnloadingItemRate
from app.models.user import User
from app.models.vendor import VendorDivision, VendorWarehouse
from app.services.rating import money

router = APIRouter(prefix="/api/vendor", tags=["vendor portal"])

PortalDep = Depends(require_capability(Capability.VENDOR_PORTAL))


def _my_vendor(user: User = Depends(get_current_user)) -> str:
    """The vendor this login belongs to, or nothing at all.

    A vendor login without a vendor on it is not a login that sees
    everything; it is a login that was made wrong, and it is refused until
    somebody fixes it. Failing closed here is the difference between a
    misconfiguration and a disclosure.
    """
    if Capability.VENDOR_PORTAL not in _caps(user):
        raise HTTPException(status_code=403, detail="This is not a vendor login")
    if user.vendor_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "This login is not linked to a vendor yet. Ask Target Express to "
                "finish setting it up."
            ),
        )
    return str(user.vendor_id)


def _caps(user: User) -> set[str]:
    from app.api.deps import capabilities_of

    return capabilities_of(user)


def _my_divisions(db: Session, vendor_id: str) -> list[str]:
    return [
        str(row)
        for row in db.execute(
            select(VendorDivision.id).where(VendorDivision.vendor_id == vendor_id)
        )
        .scalars()
        .all()
    ]


def _mine_or_404(db: Session, freight_id: str, vendor_id: str) -> Freight:
    """A freight, but only if it is theirs.

    404 rather than 403 on somebody else's: a 403 confirms the trip exists,
    which is itself something another vendor should not learn from us.
    """
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise HTTPException(status_code=404, detail="Freight not found")
    division = db.get(VendorDivision, freight.vendor_division_id)
    if division is None or str(division.vendor_id) != vendor_id:
        raise HTTPException(status_code=404, detail="Freight not found")
    return freight


# --------------------------------------------------------------------------- #
# What is happening                                                           #
# --------------------------------------------------------------------------- #


class VendorHomeOut(BaseModel):
    vendor_name: str
    divisions: list[dict]
    # The day's shape, in the terms a vendor cares about: what is still out,
    # what landed, what came back.
    running: int
    delivered_points_today: int
    returned_boxes_today: int
    awaiting_dispatch: int
    # Money, their side of it.
    invoiced_this_month: Decimal
    outstanding: Decimal
    oldest_unpaid_days: int | None


@router.get("/home", response_model=VendorHomeOut)
def home(db: Session = Depends(get_db), vendor_id: str = Depends(_my_vendor), _=PortalDep):
    from app.models.consignment import Box
    from app.models.enums import FreightPointStatus
    from app.models.vendor import Vendor

    vendor = db.get(Vendor, vendor_id)
    divisions = (
        db.execute(select(VendorDivision).where(VendorDivision.vendor_id == vendor_id))
        .scalars()
        .all()
    )
    division_ids = [d.id for d in divisions]
    today = date.today()

    def freights_where(*where):
        stmt = select(func.count()).select_from(Freight).where(
            Freight.vendor_division_id.in_(division_ids)
        )
        for clause in where:
            stmt = stmt.where(clause)
        return int(db.scalar(stmt) or 0)

    running = freights_where(
        Freight.status.in_([FreightStatus.DISPATCHED, FreightStatus.IN_TRANSIT])
    )
    awaiting = freights_where(
        Freight.status.in_([FreightStatus.DRAFT, FreightStatus.PLANNED, FreightStatus.LOADING])
    )

    delivered_today = int(
        db.scalar(
            select(func.count())
            .select_from(FreightPoint)
            .join(Freight, Freight.id == FreightPoint.freight_id)
            .where(
                Freight.vendor_division_id.in_(division_ids),
                Freight.trip_date == today,
                FreightPoint.status.in_(
                    [FreightPointStatus.DELIVERED, FreightPointStatus.PART_DELIVERED]
                ),
            )
        )
        or 0
    )

    returned_today = int(
        db.scalar(
            select(func.count())
            .select_from(Box)
            .join(Consignment, Consignment.id == Box.consignment_id)
            .where(
                Consignment.vendor_division_id.in_(division_ids),
                Box.returned_at.isnot(None),
            )
        )
        or 0
    )

    invoices = (
        db.execute(
            select(VendorInvoice).where(VendorInvoice.vendor_division_id.in_(division_ids))
        )
        .scalars()
        .all()
    )
    month_start = today.replace(day=1)
    invoiced = money(
        sum(
            (Decimal(i.total) for i in invoices if i.invoice_date >= month_start),
            Decimal("0"),
        )
    )
    unpaid = [
        i
        for i in invoices
        if i.status in (InvoiceStatus.ISSUED, InvoiceStatus.SENT)
    ]
    outstanding = money(sum((Decimal(i.total) for i in unpaid), Decimal("0")))
    oldest = min((i.invoice_date for i in unpaid), default=None)

    return VendorHomeOut(
        vendor_name=vendor.name if vendor else "—",
        divisions=[{"id": str(d.id), "name": d.name, "code": d.code} for d in divisions],
        running=running,
        delivered_points_today=delivered_today,
        returned_boxes_today=returned_today,
        awaiting_dispatch=awaiting,
        invoiced_this_month=invoiced,
        outstanding=outstanding,
        oldest_unpaid_days=(today - oldest).days if oldest else None,
    )


class VendorFreightRow(BaseModel):
    id: str
    trip_no: str
    lr_no: str | None
    trip_date: date
    status: str
    division_name: str | None
    destination_text: str | None
    point_count: int
    delivered_point_count: int
    box_count: int
    vehicle_no: str | None
    # What this run will be, or was, billed at. A vendor asking "what is this
    # costing me" should not have to wait for the invoice.
    charge: Decimal | None
    invoice_no: str | None


@router.get("/freights", response_model=list[VendorFreightRow])
def my_freights(
    status: str | None = Query(default=None),
    days: int = Query(default=60, ge=1, le=365),
    db: Session = Depends(get_db),
    vendor_id: str = Depends(_my_vendor),
    _=PortalDep,
):
    """Their own runs, newest first."""
    from app.models.billing import VendorInvoiceLine
    from app.models.consignment import Box

    division_ids = _my_divisions(db, vendor_id)
    if not division_ids:
        return []

    stmt = (
        select(Freight)
        .where(
            Freight.vendor_division_id.in_(division_ids),
            Freight.trip_date >= date.today() - timedelta(days=days),
        )
        .order_by(Freight.trip_date.desc(), Freight.trip_no.desc())
    )
    if status:
        stmt = stmt.where(Freight.status == status)

    freights = db.execute(stmt).unique().scalars().all()
    if not freights:
        return []

    ids = [f.id for f in freights]
    billed = {
        row[0]: (row[1], row[2])
        for row in db.execute(
            select(
                VendorInvoiceLine.freight_id,
                VendorInvoiceLine.line_total,
                VendorInvoice.invoice_no,
            )
            .join(VendorInvoice, VendorInvoice.id == VendorInvoiceLine.invoice_id)
            .where(VendorInvoiceLine.freight_id.in_(ids))
        ).all()
    }
    boxes = {
        row[0]: row[1]
        for row in db.execute(
            select(Consignment.freight_point_id, func.count(Box.id))
            .join(Box, Box.consignment_id == Consignment.id)
            .where(Consignment.freight_point_id.isnot(None))
            .group_by(Consignment.freight_point_id)
        ).all()
    }
    division_names = {
        str(d.id): d.name
        for d in db.execute(
            select(VendorDivision).where(VendorDivision.id.in_(division_ids))
        )
        .scalars()
        .all()
    }

    out: list[VendorFreightRow] = []
    for f in freights:
        line = billed.get(f.id)
        out.append(
            VendorFreightRow(
                id=str(f.id),
                trip_no=f.trip_no,
                lr_no=f.lr_no,
                trip_date=f.trip_date,
                status=str(f.status),
                division_name=division_names.get(str(f.vendor_division_id)),
                destination_text=f.destination_text,
                point_count=f.point_count,
                delivered_point_count=f.delivered_point_count,
                box_count=sum(boxes.get(p.id, 0) for p in f.points),
                vehicle_no=next(
                    (leg.vehicle.registration_no for leg in f.legs if leg.vehicle), None
                ),
                charge=line[0] if line else None,
                invoice_no=line[1] if line else None,
            )
        )
    return out


class PointDetailOut(BaseModel):
    """One stop, as the vendor's own customer experienced it."""

    sequence: int
    customer_name: str
    address: str | None
    floor_number: int
    status: str
    loaded_box_count: int
    delivered_box_count: int
    receiver_name: str | None
    arrived_at: str | None
    departed_at: str | None
    # The evidence. Photographs taken at the door are the whole reason a
    # vendor stops ringing to ask whether something actually arrived.
    loading_photo_url: str | None
    delivery_photo_url: str | None
    signature_url: str | None
    # What the customer said, unprompted, from their own tracking link.
    customer_rating: int | None
    customer_remarks: str | None
    bills: list[str]
    unloading_billed: Decimal
    coolie_billed: Decimal
    coolie_note: str | None


class VendorFreightOut(VendorFreightRow):
    driver_name: str | None
    start_km: int | None
    close_km: int | None
    km: int
    points: list[PointDetailOut]


@router.get("/freights/{freight_id}", response_model=VendorFreightOut)
def my_freight(
    freight_id: str,
    db: Session = Depends(get_db),
    vendor_id: str = Depends(_my_vendor),
    _=PortalDep,
):
    """One run, with the evidence from every door on it."""
    from app.models.billing import VendorInvoiceLine
    from app.models.consignment import Box

    freight = _mine_or_404(db, freight_id, vendor_id)
    leg = freight.legs[0] if freight.legs else None
    line = db.execute(
        select(VendorInvoiceLine, VendorInvoice.invoice_no)
        .join(VendorInvoice, VendorInvoice.id == VendorInvoiceLine.invoice_id)
        .where(VendorInvoiceLine.freight_id == freight.id)
    ).first()

    division = db.get(VendorDivision, freight.vendor_division_id)

    points: list[PointDetailOut] = []
    for p in freight.points:
        bills = (
            db.execute(
                select(Consignment.vendor_bill_no)
                .where(Consignment.freight_point_id == p.id)
                .order_by(Consignment.vendor_bill_no)
            )
            .scalars()
            .all()
        )
        loaded = int(
            db.scalar(
                select(func.count())
                .select_from(Box)
                .join(Consignment, Consignment.id == Box.consignment_id)
                .where(Consignment.freight_point_id == p.id)
            )
            or 0
        )
        points.append(
            PointDetailOut(
                sequence=p.sequence,
                customer_name=p.consignee.name if p.consignee else "—",
                address=p.address_snapshot,
                floor_number=p.floor_number,
                status=str(p.status),
                loaded_box_count=loaded or p.loaded_box_count,
                delivered_box_count=p.delivered_box_count,
                receiver_name=p.receiver_name,
                arrived_at=p.arrived_at.isoformat() if p.arrived_at else None,
                departed_at=p.departed_at.isoformat() if p.departed_at else None,
                loading_photo_url=p.loading_photo_url,
                delivery_photo_url=p.delivery_photo_url,
                signature_url=p.signature_url,
                customer_rating=p.customer_rating,
                customer_remarks=p.customer_remarks,
                bills=list(bills),
                unloading_billed=Decimal(p.unloading_billed or 0),
                coolie_billed=Decimal(p.coolie_billed or 0),
                coolie_note=p.coolie_note,
            )
        )

    return VendorFreightOut(
        id=str(freight.id),
        trip_no=freight.trip_no,
        lr_no=freight.lr_no,
        trip_date=freight.trip_date,
        status=str(freight.status),
        division_name=division.name if division else None,
        destination_text=freight.destination_text,
        point_count=freight.point_count,
        delivered_point_count=freight.delivered_point_count,
        box_count=sum(p.loaded_box_count for p in points),
        vehicle_no=leg.vehicle.registration_no if leg and leg.vehicle else None,
        charge=line[0].line_total if line else None,
        invoice_no=line[1] if line else None,
        driver_name=leg.driver.name if leg and leg.driver else None,
        start_km=leg.start_odometer if leg else None,
        close_km=leg.end_odometer if leg else None,
        km=freight.total_km or freight.round_trip_km,
        points=points,
    )


# --------------------------------------------------------------------------- #
# Raising a run                                                               #
# --------------------------------------------------------------------------- #


class VendorPointIn(BaseModel):
    consignee_id: str | None = None
    # A dealer we have never delivered to. Three things, as everywhere else:
    # a name, a town and a mobile.
    new_customer_name: str | None = Field(default=None, max_length=200)
    new_customer_city: str | None = Field(default=None, max_length=120)
    new_customer_phone: str | None = Field(default=None, max_length=20)
    floor_number: int = Field(default=0, ge=0, le=100)
    bill_no: str | None = Field(default=None, max_length=64)
    box_count: int = Field(default=0, ge=0, le=999)


class VendorFreightIn(BaseModel):
    vendor_division_id: str
    warehouse_id: str
    trip_date: date
    points: list[VendorPointIn] = Field(min_length=1)
    remarks: str | None = Field(default=None, max_length=500)


@router.post("/freights", response_model=VendorFreightRow, status_code=201)
def raise_freight(
    payload: VendorFreightIn,
    db: Session = Depends(get_db),
    vendor_id: str = Depends(_my_vendor),
    user: User = Depends(get_current_user),
    _=PortalDep,
):
    """A vendor putting tomorrow's run in themselves.

    They know what is going out before we do, and the alternative is a phone
    call that somebody retypes. It arrives as a DRAFT: Target Express assigns
    the lorry, prints the labels and dispatches, because those are ours and a
    vendor pressing dispatch would be a vendor telling us a lorry has left.
    """
    import secrets

    from app.api.routes.daysheet import _next_trip_no
    from app.models.consignment import Box, Consignment
    from app.models.enums import BoxStatus, ConsigneeType, ConsignmentStatus, GeoConfidence

    division = db.get(VendorDivision, payload.vendor_division_id)
    if division is None or str(division.vendor_id) != vendor_id:
        raise HTTPException(status_code=404, detail="Division not found")

    warehouse = db.get(VendorWarehouse, payload.warehouse_id)
    if warehouse is None or str(warehouse.vendor_id) != vendor_id:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    for point in payload.points:
        if point.consignee_id is None and not (point.new_customer_name or "").strip():
            raise HTTPException(
                status_code=422, detail="Every stop needs a customer or a name"
            )

    freight = Freight(
        trip_no=_next_trip_no(db, payload.trip_date),
        trip_date=payload.trip_date,
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.DRAFT,
        point_count=len(payload.points),
        created_by_id=user.id,
        remarks=payload.remarks,
    )
    db.add(freight)
    db.flush()

    places: list[str] = []
    for sequence, row in enumerate(payload.points, start=1):
        if row.consignee_id:
            consignee = db.get(Consignee, row.consignee_id)
            if consignee is None:
                raise HTTPException(status_code=404, detail="Customer not found")
        else:
            consignee = Consignee(
                name=row.new_customer_name.strip(),
                type=ConsigneeType.RETAIL_CUSTOMER,
                city=(row.new_customer_city or "").strip() or None,
                phone=(row.new_customer_phone or "").strip() or None,
                geo_confidence=GeoConfidence.UNVERIFIED,
                is_active=True,
            )
            db.add(consignee)
            db.flush()

        point = FreightPoint(
            freight_id=freight.id,
            sequence=sequence,
            consignee_id=consignee.id,
            floor_number=row.floor_number,
            address_snapshot=consignee.address or consignee.city,
            latitude=consignee.latitude,
            longitude=consignee.longitude,
        )
        db.add(point)
        db.flush()
        if consignee.city or consignee.name:
            places.append(consignee.city or consignee.name)

        if row.bill_no and row.box_count:
            consignment = Consignment(
                vendor_division_id=division.id,
                warehouse_id=warehouse.id,
                consignee_id=consignee.id,
                freight_point_id=point.id,
                vendor_bill_no=row.bill_no,
                bill_date=payload.trip_date,
                declared_box_count=row.box_count,
                status=ConsignmentStatus.RECEIVED,
            )
            db.add(consignment)
            db.flush()
            token = secrets.token_hex(3).upper()
            for n in range(1, row.box_count + 1):
                db.add(
                    Box(
                        consignment_id=consignment.id,
                        item_no=n,
                        barcode=f"TE-{token}-{n:03d}",
                        status=BoxStatus.SORTED,
                    )
                )
            point.loaded_box_count += row.box_count

    seen: list[str] = []
    for place in places:
        if place and place not in seen:
            seen.append(place)
    freight.destination_text = ", ".join(seen)[:500] or None

    db.commit()
    db.refresh(freight)

    return VendorFreightRow(
        id=str(freight.id),
        trip_no=freight.trip_no,
        lr_no=freight.lr_no,
        trip_date=freight.trip_date,
        status=str(freight.status),
        division_name=division.name,
        destination_text=freight.destination_text,
        point_count=freight.point_count,
        delivered_point_count=0,
        box_count=sum(p.loaded_box_count for p in freight.points),
        vehicle_no=None,
        charge=None,
        invoice_no=None,
    )


# --------------------------------------------------------------------------- #
# What was agreed, and what has been billed                                   #
# --------------------------------------------------------------------------- #


class VendorRateOut(BaseModel):
    division_name: str
    vehicle_type: str | None
    effective_from: date
    effective_to: date | None
    base_trip_amount: Decimal
    included_km: int
    extra_km_rate: Decimal
    included_points: int
    extra_point_rate: Decimal
    unloading_basis: str


@router.get("/rate-cards", response_model=list[VendorRateOut])
def my_rates(db: Session = Depends(get_db), vendor_id: str = Depends(_my_vendor), _=PortalDep):
    """What was agreed. Read-only, and not by accident.

    A rate is an agreement between two companies. One of them editing it
    alone is not a rate change — it is a dispute discovered at invoice time.
    """
    from app.models.fleet import VehicleType

    division_ids = _my_divisions(db, vendor_id)
    if not division_ids:
        return []

    names = {
        str(d.id): d.name
        for d in db.execute(
            select(VendorDivision).where(VendorDivision.id.in_(division_ids))
        )
        .scalars()
        .all()
    }
    types = {str(t.id): t.name for t in db.execute(select(VehicleType)).scalars().all()}

    rows = (
        db.execute(
            select(RateCard)
            .where(
                RateCard.vendor_division_id.in_(division_ids),
                RateCard.is_active.is_(True),
            )
            .order_by(RateCard.effective_from.desc())
        )
        .scalars()
        .all()
    )
    return [
        VendorRateOut(
            division_name=names.get(str(r.vendor_division_id), "—"),
            vehicle_type=types.get(str(r.vehicle_type_id)) if r.vehicle_type_id else None,
            effective_from=r.effective_from,
            effective_to=r.effective_to,
            base_trip_amount=r.base_trip_amount,
            included_km=r.included_km,
            extra_km_rate=r.extra_km_rate,
            included_points=r.included_points,
            extra_point_rate=r.extra_point_rate,
            unloading_basis=str(r.unloading_basis),
        )
        for r in rows
    ]


class VendorUnloadingRateOut(BaseModel):
    division_name: str
    item_name: str
    base_rate: Decimal
    per_floor_rate: Decimal
    max_chargeable_floors: int
    charge_floors_with_lift: bool


@router.get("/unloading-rates", response_model=list[VendorUnloadingRateOut])
def my_unloading_rates(
    db: Session = Depends(get_db), vendor_id: str = Depends(_my_vendor), _=PortalDep
):
    """What unloading costs them, per article and per floor.

    Their side only. What the driver is paid for carrying it is Target
    Express's own arrangement and is not on this screen.
    """
    division_ids = _my_divisions(db, vendor_id)
    if not division_ids:
        return []

    names = {
        str(d.id): d.name
        for d in db.execute(
            select(VendorDivision).where(VendorDivision.id.in_(division_ids))
        )
        .scalars()
        .all()
    }
    rows = (
        db.execute(
            select(UnloadingItemRate)
            .where(
                UnloadingItemRate.vendor_division_id.in_(division_ids),
                UnloadingItemRate.is_active.is_(True),
            )
            .order_by(UnloadingItemRate.item_name)
        )
        .scalars()
        .all()
    )
    return [
        VendorUnloadingRateOut(
            division_name=names.get(str(r.vendor_division_id), "—"),
            item_name=r.item_name,
            base_rate=r.base_rate,
            per_floor_rate=r.per_floor_rate,
            max_chargeable_floors=r.max_chargeable_floors,
            charge_floors_with_lift=bool(r.charge_floors_with_lift),
        )
        for r in rows
    ]


class VendorInvoiceRow(BaseModel):
    id: str
    invoice_no: str
    invoice_date: date
    period_from: date
    period_to: date
    division_name: str | None
    taxable_value: Decimal
    zero_rated_value: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal
    status: str
    line_count: int
    paid_on: date | None
    amount_received: Decimal | None
    # What is still owed on this one.
    balance: Decimal
    days_outstanding: int | None


@router.get("/invoices", response_model=list[VendorInvoiceRow])
def my_invoices(
    db: Session = Depends(get_db), vendor_id: str = Depends(_my_vendor), _=PortalDep
):
    """What they have been billed, and what is still open.

    Drafts are left out. A draft is a working copy Target Express has not
    sent, and a vendor seeing a number that may still change before it
    reaches them is how an argument starts over a figure nobody meant.
    """
    division_ids = _my_divisions(db, vendor_id)
    if not division_ids:
        return []

    names = {
        str(d.id): d.name
        for d in db.execute(
            select(VendorDivision).where(VendorDivision.id.in_(division_ids))
        )
        .scalars()
        .all()
    }
    rows = (
        db.execute(
            select(VendorInvoice)
            .where(
                VendorInvoice.vendor_division_id.in_(division_ids),
                VendorInvoice.status != InvoiceStatus.DRAFT,
            )
            .order_by(VendorInvoice.invoice_date.desc())
        )
        .unique()
        .scalars()
        .all()
    )

    today = date.today()
    return [
        VendorInvoiceRow(
            id=str(i.id),
            invoice_no=i.invoice_no,
            invoice_date=i.invoice_date,
            period_from=i.period_from,
            period_to=i.period_to,
            division_name=names.get(str(i.vendor_division_id)),
            taxable_value=i.taxable_value,
            zero_rated_value=i.zero_rated_value,
            cgst=i.cgst,
            sgst=i.sgst,
            igst=i.igst,
            total=i.total,
            status=str(i.status),
            line_count=len(i.lines),
            paid_on=i.paid_on,
            amount_received=i.amount_received,
            balance=money(Decimal(i.total) - Decimal(i.amount_received or 0)),
            days_outstanding=(
                (today - i.invoice_date).days
                if i.status in (InvoiceStatus.ISSUED, InvoiceStatus.SENT)
                else None
            ),
        )
        for i in rows
    ]
