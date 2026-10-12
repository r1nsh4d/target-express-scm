"""The day sheet: a morning's bills entered in one go.

The old path was a dialog per bill — pick a division, pick a warehouse, find
the customer in a list of two hundred, type the number, type the count, save,
repeat. Thirty bills is thirty round trips, and then the freight is built
separately and the bills attached to it separately again, which is the step
people miss.

This is the same work in two calls. `parse` reads what was typed and says what
it understood, line by line, with nothing created. `commit` creates it — the
customers that are new, the bills, the boxes under them, the freight, its
stops, and the attachment of each bill to its stop — in one transaction.

One transaction, deliberately. Half a day sheet is worse than none: nobody can
tell by looking which half went in, and the natural response is to type it all
again and end up with the good half twice.
"""

from __future__ import annotations

import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WAREHOUSE_ROLES, require_roles
from app.db.session import get_db
from app.models.consignee import Consignee
from app.models.consignment import Box, Consignment
from app.models.enums import (
    BoxStatus,
    ConsigneeType,
    ConsignmentStatus,
    FreightStatus,
    GeoConfidence,
)
from app.models.freight import Freight, FreightPoint
from app.models.user import User
from app.models.vendor import VendorDivision, VendorWarehouse
from app.services import daysheet
from app.api.routes.freights import _next_trip_no

router = APIRouter(prefix="/api/daysheet", tags=["daysheet"])

OpsDep = Depends(require_roles(*WAREHOUSE_ROLES))


# --------------------------------------------------------------------------- #
# Reading                                                                     #
# --------------------------------------------------------------------------- #

class ParseIn(BaseModel):
    text: str = Field(max_length=50_000)
    # Scopes the duplicate check: a bill number is unique per division, so
    # knowing the division turns "is this already entered?" from a guess into
    # an answer.
    vendor_division_id: str | None = None


class CustomerMatchOut(BaseModel):
    consignee_id: str | None
    name: str
    score: float
    alternatives: list[dict] = []


class ParsedLineOut(BaseModel):
    line_no: int
    raw: str
    vendor_bill_no: str | None
    customer_text: str
    match: CustomerMatchOut | None
    box_count: int | None
    item_name: str | None
    problems: list[str]


class ParseOut(BaseModel):
    lines: list[ParsedLineOut]
    # Totals for the header, so the figure on screen is the figure that will be
    # created rather than something counted again by hand.
    bill_count: int
    box_count: int
    stop_count: int
    needs_attention: int


@router.post("/parse", response_model=ParseOut)
def parse(payload: ParseIn, db: Session = Depends(get_db), _=OpsDep) -> ParseOut:
    """Read the sheet. Creates nothing."""
    customers = [
        {"id": str(c.id), "name": c.name, "city": c.city}
        for c in db.execute(
            select(Consignee).where(Consignee.is_active.is_(True))
        ).scalars()
    ]

    rows = daysheet.parse_sheet(payload.text, customers)

    # Bills already in the system for this division. Caught here rather than at
    # save, because finding out after typing forty lines is the worst moment.
    if payload.vendor_division_id:
        existing = {
            bill
            for (bill,) in db.execute(
                select(Consignment.vendor_bill_no).where(
                    Consignment.vendor_division_id == payload.vendor_division_id
                )
            )
        }
        for row in rows:
            if row.vendor_bill_no and row.vendor_bill_no in existing:
                row.problems.append(
                    f"Bill {row.vendor_bill_no} is already entered for this division"
                )

    # A customer nobody has entered yet is still a stop. Counting only the
    # matched ones made the summary disagree with what the next button
    # actually created — it said four stops and built five.
    stops = {
        row.match.consignee_id
        if row.match and row.match.consignee_id
        else daysheet.normalise(row.customer_text)
        for row in rows
        if (row.match and row.match.consignee_id) or row.customer_text.strip()
    }

    return ParseOut(
        lines=[
            ParsedLineOut(
                line_no=row.line_no,
                raw=row.raw,
                vendor_bill_no=row.vendor_bill_no,
                customer_text=row.customer_text,
                match=(
                    CustomerMatchOut(
                        consignee_id=row.match.consignee_id,
                        name=row.match.name,
                        score=row.match.score,
                        alternatives=row.match.alternatives,
                    )
                    if row.match
                    else None
                ),
                box_count=row.box_count,
                item_name=row.item_name,
                problems=row.problems,
            )
            for row in rows
        ],
        bill_count=len(rows),
        box_count=sum(r.box_count or 0 for r in rows),
        stop_count=len(stops),
        needs_attention=sum(1 for r in rows if r.needs_attention),
    )


# --------------------------------------------------------------------------- #
# Creating                                                                    #
# --------------------------------------------------------------------------- #

class NewCustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    city: str | None = None
    phone: str | None = None


class DayRowIn(BaseModel):
    vendor_bill_no: str = Field(min_length=1, max_length=64)
    box_count: int = Field(ge=1, le=999)
    item_name: str | None = None
    # One or the other. An id uses a customer already on file; a block of
    # details creates one.
    consignee_id: str | None = None
    new_customer: NewCustomerIn | None = None


class CommitIn(BaseModel):
    vendor_division_id: str
    warehouse_id: str
    rows: list[DayRowIn] = Field(min_length=1)

    # Everything below is the freight. Without it the bills are simply entered
    # and left waiting, which is what you want when the lorry is not decided.
    create_freight: bool = True
    trip_date: date | None = None
    # Delivery order, as consignee ids. Anything not named keeps the order it
    # first appeared in on the sheet.
    stop_order: list[str] = []
    floors: dict[str, int] = {}


class CommitOut(BaseModel):
    consignment_count: int
    box_count: int
    customers_created: int
    freight_id: str | None
    trip_no: str | None
    stop_count: int


@router.post("/commit", response_model=CommitOut, status_code=201)
def commit(payload: CommitIn, db: Session = Depends(get_db), user: User = OpsDep):
    """Create the whole day sheet, or none of it."""
    division = db.get(VendorDivision, payload.vendor_division_id)
    if division is None:
        raise HTTPException(status_code=404, detail="Vendor division not found")
    warehouse = db.get(VendorWarehouse, payload.warehouse_id)
    if warehouse is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    # Checked before anything is written, so a refusal leaves the database as it
    # was rather than part-filled.
    seen: set[str] = set()
    for row in payload.rows:
        if row.vendor_bill_no in seen:
            raise HTTPException(
                status_code=409,
                detail=f"Bill {row.vendor_bill_no} appears twice on this sheet",
            )
        seen.add(row.vendor_bill_no)

        if row.consignee_id is None and row.new_customer is None:
            raise HTTPException(
                status_code=422,
                detail=f"Bill {row.vendor_bill_no} has no customer",
            )

    clash = db.execute(
        select(Consignment.vendor_bill_no).where(
            Consignment.vendor_division_id == division.id,
            Consignment.vendor_bill_no.in_(seen),
        )
    ).scalars().first()
    if clash is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Bill {clash} is already entered for {division.name}",
        )

    customers_created = 0
    consignments: list[tuple[Consignment, str]] = []
    total_boxes = 0

    # New customers created during THIS sheet, by name.
    #
    # A new dealer with two bills is named on two lines, and without this each
    # line created its own customer — so the dealer existed twice, the freight
    # got two stops for one address, and the vendor was charged for two points
    # instead of one. A billing error, not a tidiness problem.
    #
    # Matched on a squashed-down name so that "Vadakara Furniture House" and
    # "vadakara  furniture house" are the same dealer, which is how the same
    # name gets typed twice in one sitting.
    fresh: dict[str, Consignee] = {}

    def key(name: str) -> str:
        return " ".join(name.lower().split())

    for row in payload.rows:
        if row.consignee_id is not None:
            consignee = db.get(Consignee, row.consignee_id)
            if consignee is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Customer not found for bill {row.vendor_bill_no}",
                )
        elif key(row.new_customer.name) in fresh:
            consignee = fresh[key(row.new_customer.name)]
        else:
            consignee = Consignee(
                name=row.new_customer.name.strip(),
                type=ConsigneeType.RETAIL_CUSTOMER,
                city=(row.new_customer.city or "").strip() or None,
                phone=(row.new_customer.phone or "").strip() or None,
                # Entered from a bill, with nobody looking at a map. Marked
                # unverified so it shows up to be pinned rather than being
                # trusted as a delivery location.
                geo_confidence=GeoConfidence.UNVERIFIED,
                is_active=True,
            )
            db.add(consignee)
            db.flush()
            fresh[key(row.new_customer.name)] = consignee
            customers_created += 1

        consignment = Consignment(
            vendor_division_id=division.id,
            warehouse_id=warehouse.id,
            consignee_id=consignee.id,
            vendor_bill_no=row.vendor_bill_no,
            bill_date=payload.trip_date or date.today(),
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
                    item_name=row.item_name,
                    item_code=(
                        row.item_name.upper().replace(" ", "_") if row.item_name else None
                    ),
                    status=BoxStatus.SORTED,
                )
            )
        total_boxes += row.box_count
        consignments.append((consignment, str(consignee.id)))

    freight: Freight | None = None
    stop_count = 0

    if payload.create_freight:
        # One stop per customer, however many bills they have. The charge is per
        # point, so splitting a customer's two bills into two stops would
        # overcharge the vendor and they would query the invoice.
        order: list[str] = []
        for consignee_id in payload.stop_order:
            if consignee_id not in order:
                order.append(consignee_id)
        for _, consignee_id in consignments:
            if consignee_id not in order:
                order.append(consignee_id)

        trip_date = payload.trip_date or date.today()
        freight = Freight(
            trip_no=_next_trip_no(db, trip_date),
            trip_date=trip_date,
            vendor_division_id=division.id,
            warehouse_id=warehouse.id,
            status=FreightStatus.DRAFT,
            point_count=len(order),
            created_by_id=user.id,
        )
        db.add(freight)
        db.flush()

        points: dict[str, FreightPoint] = {}
        for sequence, consignee_id in enumerate(order, start=1):
            point = FreightPoint(
                freight_id=freight.id,
                sequence=sequence,
                consignee_id=consignee_id,
                floor_number=payload.floors.get(consignee_id, 0),
            )
            db.add(point)
            db.flush()
            points[consignee_id] = point

        # The step everyone forgets, done here as part of the same action.
        for consignment, consignee_id in consignments:
            point = points[consignee_id]
            consignment.freight_point_id = point.id
            point.loaded_box_count += consignment.declared_box_count

        stop_count = len(order)

    db.commit()

    return CommitOut(
        consignment_count=len(consignments),
        box_count=total_boxes,
        customers_created=customers_created,
        freight_id=str(freight.id) if freight else None,
        trip_no=freight.trip_no if freight else None,
        stop_count=stop_count,
    )
