"""Consignments, the boxes under them, and the labels that get pasted on.

A consignment is one vendor bill, for one delivery point, covering a number of
boxes. Creating it generates a Box row per carton, because the label and the
count at both checkpoints hang off those rows.
"""

import secrets
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import BACK_OFFICE_ROLES, WAREHOUSE_ROLES, require_roles
from app.db.session import get_db
from app.models.consignee import Consignee
from app.models.consignment import Box, Consignment
from app.models.enums import BoxStatus, ConsignmentStatus
from app.models.freight import Freight, FreightPoint
from app.models.vendor import VendorDivision, VendorWarehouse
from app.schemas.base import ORMModel

router = APIRouter(prefix="/api", tags=["consignments"])

ReadDep = Depends(require_roles(*BACK_OFFICE_ROLES))
OpsDep = Depends(require_roles(*WAREHOUSE_ROLES))

# Colours cycle by point sequence. Loaders sort by colour and number long before
# anyone reads a barcode, so this is the label's most important element.
POINT_COLOURS = [
    "#E11D48", "#2563EB", "#16A34A", "#D97706", "#7C3AED",
    "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#4F46E5",
]


class ConsignmentIn(BaseModel):
    vendor_division_id: str
    warehouse_id: str
    consignee_id: str
    vendor_bill_no: str = Field(min_length=1, max_length=64)
    bill_date: date
    box_count: int = Field(ge=1, le=999)
    goods_category_id: str | None = None
    declared_value: Decimal | None = None
    eway_bill_no: str | None = None
    remarks: str | None = None
    # Furniture is priced per article, so the label and the unloading charge
    # need to know what each box actually is.
    item_code: str | None = None
    item_name: str | None = None


class BoxOut(ORMModel):
    id: str
    item_no: int
    barcode: str
    item_code: str | None
    item_name: str | None
    status: BoxStatus


class ConsignmentOut(ORMModel):
    id: str
    vendor_division_id: str
    warehouse_id: str
    consignee_id: str
    consignee_name: str | None = None
    vendor_bill_no: str
    bill_date: date
    declared_box_count: int
    eway_bill_no: str | None
    status: ConsignmentStatus
    freight_point_id: str | None
    remarks: str | None


class AssignIn(BaseModel):
    consignment_ids: list[str] = Field(min_length=1)


class LabelOut(BaseModel):
    """One sticker."""

    barcode: str
    point_sequence: int
    point_colour: str
    consignee_name: str
    city: str | None
    vendor_bill_no: str
    item_no: int
    of_total: int
    item_name: str | None
    trip_no: str
    lr_no: str | None
    floor_number: int


def _out(c: Consignment) -> ConsignmentOut:
    o = ConsignmentOut.model_validate(c)
    o.consignee_name = c.consignee.name if c.consignee else None
    return o


@router.get("/consignments", response_model=list[ConsignmentOut])
def list_consignments(
    vendor_division_id: str | None = None,
    unassigned: bool = Query(default=False, description="Only those not yet on a freight"),
    limit: int = Query(default=200, le=500),
    db: Session = Depends(get_db),
    _=ReadDep,
):
    stmt = (
        select(Consignment)
        .options(joinedload(Consignment.consignee))
        .order_by(Consignment.bill_date.desc(), Consignment.created_at.desc())
        .limit(limit)
    )
    if vendor_division_id:
        stmt = stmt.where(Consignment.vendor_division_id == vendor_division_id)
    if unassigned:
        stmt = stmt.where(Consignment.freight_point_id.is_(None))

    return [_out(c) for c in db.execute(stmt).unique().scalars().all()]


@router.post("/consignments", response_model=ConsignmentOut, status_code=201)
def create_consignment(payload: ConsignmentIn, db: Session = Depends(get_db), _=OpsDep):
    """Create the bill and generate one box per carton.

    The boxes are what get labelled and counted; without them there is nothing
    to reconcile at either end.
    """
    for model, obj_id, label in (
        (VendorDivision, payload.vendor_division_id, "Vendor division"),
        (VendorWarehouse, payload.warehouse_id, "Warehouse"),
        (Consignee, payload.consignee_id, "Customer"),
    ):
        if db.get(model, obj_id) is None:
            raise HTTPException(status_code=404, detail=f"{label} not found")

    duplicate = db.execute(
        select(Consignment).where(
            Consignment.vendor_division_id == payload.vendor_division_id,
            Consignment.vendor_bill_no == payload.vendor_bill_no,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Bill {payload.vendor_bill_no} already exists for this division",
        )

    consignment = Consignment(
        vendor_division_id=payload.vendor_division_id,
        warehouse_id=payload.warehouse_id,
        consignee_id=payload.consignee_id,
        goods_category_id=payload.goods_category_id,
        vendor_bill_no=payload.vendor_bill_no,
        bill_date=payload.bill_date,
        declared_box_count=payload.box_count,
        declared_value=payload.declared_value,
        eway_bill_no=payload.eway_bill_no,
        remarks=payload.remarks,
        status=ConsignmentStatus.RECEIVED,
    )
    db.add(consignment)
    db.flush()

    token = secrets.token_hex(3).upper()
    for n in range(1, payload.box_count + 1):
        db.add(
            Box(
                consignment_id=consignment.id,
                item_no=n,
                # Readable on the sticker and unique across the system.
                barcode=f"TE-{token}-{n:03d}",
                item_code=payload.item_code,
                item_name=payload.item_name,
                status=BoxStatus.SORTED,
            )
        )

    db.commit()
    db.refresh(consignment)
    return _out(consignment)


@router.get("/consignments/{consignment_id}/boxes", response_model=list[BoxOut])
def list_boxes(consignment_id: str, db: Session = Depends(get_db), _=ReadDep):
    rows = (
        db.execute(select(Box).where(Box.consignment_id == consignment_id).order_by(Box.item_no))
        .scalars()
        .all()
    )
    return [BoxOut.model_validate(b) for b in rows]


@router.post("/freights/{freight_id}/points/{point_id}/consignments", status_code=204)
def assign_consignments(
    freight_id: str,
    point_id: str,
    payload: AssignIn,
    db: Session = Depends(get_db),
    _=OpsDep,
):
    """Put bills onto a stop, and set that stop's planned box count from them."""
    point = db.get(FreightPoint, point_id)
    if point is None or str(point.freight_id) != str(freight_id):
        raise HTTPException(status_code=404, detail="Point not found on this freight")

    total = 0
    for cid in payload.consignment_ids:
        consignment = db.get(Consignment, cid)
        if consignment is None:
            raise HTTPException(status_code=404, detail=f"Consignment {cid} not found")
        if str(consignment.consignee_id) != str(point.consignee_id):
            raise HTTPException(
                status_code=409,
                detail=f"Bill {consignment.vendor_bill_no} is for a different customer",
            )
        consignment.freight_point_id = point.id
        consignment.status = ConsignmentStatus.ASSIGNED
        total += consignment.declared_box_count

    point.loaded_box_count = total
    db.commit()


@router.get("/freights/{freight_id}/labels", response_model=list[LabelOut])
def freight_labels(freight_id: str, db: Session = Depends(get_db), _=OpsDep):
    """Every sticker for a freight, in the order they should be printed.

    Ordered by point then box number, so the printed stack matches the order the
    crew sorts them into.
    """
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise HTTPException(status_code=404, detail="Freight not found")

    labels: list[LabelOut] = []
    for point in sorted(freight.points, key=lambda p: p.sequence):
        colour = POINT_COLOURS[(point.sequence - 1) % len(POINT_COLOURS)]

        consignments = (
            db.execute(
                select(Consignment)
                .options(joinedload(Consignment.boxes))
                .where(Consignment.freight_point_id == point.id)
                .order_by(Consignment.vendor_bill_no)
            )
            .unique()
            .scalars()
            .all()
        )

        for consignment in consignments:
            total = len(consignment.boxes)
            for box in sorted(consignment.boxes, key=lambda b: b.item_no):
                labels.append(
                    LabelOut(
                        barcode=box.barcode,
                        point_sequence=point.sequence,
                        point_colour=colour,
                        consignee_name=point.consignee.name,
                        city=point.consignee.city,
                        vendor_bill_no=consignment.vendor_bill_no,
                        item_no=box.item_no,
                        of_total=total,
                        item_name=box.item_name,
                        trip_no=freight.trip_no,
                        lr_no=freight.lr_no,
                        floor_number=point.floor_number,
                    )
                )

    return labels


class SortingSummaryOut(BaseModel):
    point_sequence: int
    point_colour: str
    consignee_name: str
    bill_count: int
    box_count: int


@router.get("/freights/{freight_id}/sorting", response_model=list[SortingSummaryOut])
def sorting_summary(freight_id: str, db: Session = Depends(get_db), _=OpsDep):
    """What the crew needs at the sorting table: how many boxes to each point."""
    freight = db.get(Freight, freight_id)
    if freight is None:
        raise HTTPException(status_code=404, detail="Freight not found")

    out: list[SortingSummaryOut] = []
    for point in sorted(freight.points, key=lambda p: p.sequence):
        bills, boxes = db.execute(
            select(func.count(func.distinct(Consignment.id)), func.count(Box.id))
            .select_from(Consignment)
            .outerjoin(Box, Box.consignment_id == Consignment.id)
            .where(Consignment.freight_point_id == point.id)
        ).one()

        out.append(
            SortingSummaryOut(
                point_sequence=point.sequence,
                point_colour=POINT_COLOURS[(point.sequence - 1) % len(POINT_COLOURS)],
                consignee_name=point.consignee.name,
                bill_count=bills or 0,
                box_count=boxes or 0,
            )
        )
    return out
