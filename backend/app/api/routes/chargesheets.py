"""Unloading charge sheets, for the office and for the invoice.

Three ways in, all answering the same question from different places:

  * by invoice — what gets printed behind the tax invoice and sent to the
    vendor, so the unloading line has its working attached;
  * by freight — one trip's sheets, for a query about a single run;
  * by a set of freights — what the invoice preview shows before anybody
    creates the invoice, so the office can see what the vendor will be asked
    to accept.

Read-only. Nothing here prices anything or changes a figure; it assembles what
was recorded at the door into the shape of the form the dealer already signs.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import BACK_OFFICE_ROLES, require_roles
from app.db.session import get_db
from app.models.billing import VendorInvoice
from app.models.freight import Freight
from app.services.chargesheet import (
    ChargeSheet,
    sheets_for_freights,
    sheets_for_invoice,
)

router = APIRouter(prefix="/api", tags=["unloading sheets"])

ReadDep = Depends(require_roles(*BACK_OFFICE_ROLES))


class SheetLineOut(BaseModel):
    item_code: str
    item_name: str
    quantity: int
    base_rate: Decimal
    floors_charged: int
    per_floor_rate: Decimal
    unit_charge: Decimal
    amount: Decimal


class ChargeSheetOut(BaseModel):
    point_id: str
    trip_no: str
    lr_no: str | None
    trip_date: str
    vehicle_no: str
    customer_name: str
    location: str | None
    vendor_bill_nos: list[str]
    bill_date: str | None
    floor_number: int
    has_lift: bool
    lines: list[SheetLineOut]
    item_count: int
    billed_total: Decimal
    rebuilt_total: Decimal
    # True when the working adds up to what the vendor was charged. False is
    # not an error — an office correction after the driver saved his sheet is
    # a real thing — but it is something the screen has to say out loud.
    agrees_with_invoice: bool
    unpriced_item_codes: list[str]
    coolie_billed: Decimal
    coolie_note: str | None
    receiver_name: str | None
    delivered_on: str | None


def _out(sheet: ChargeSheet) -> ChargeSheetOut:
    return ChargeSheetOut(
        **{
            **sheet.__dict__,
            "lines": [SheetLineOut(**line.__dict__) for line in sheet.lines],
            "item_count": sheet.item_count,
            "agrees_with_invoice": sheet.agrees_with_invoice,
        }
    )


@router.get("/invoices/{invoice_id}/unloading-sheets", response_model=list[ChargeSheetOut])
def sheets_behind_an_invoice(invoice_id: str, db: Session = Depends(get_db), _=ReadDep):
    """What prints behind the tax invoice."""
    invoice = db.get(VendorInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return [_out(s) for s in sheets_for_invoice(db, invoice)]


@router.get("/freights/{freight_id}/unloading-sheets", response_model=list[ChargeSheetOut])
def sheets_for_one_freight(freight_id: str, db: Session = Depends(get_db), _=ReadDep):
    """One trip's sheets, for answering a query about a single run."""
    if db.get(Freight, freight_id) is None:
        raise HTTPException(status_code=404, detail="Freight not found")
    return [_out(s) for s in sheets_for_freights(db, [freight_id])]


@router.get("/unloading-sheets", response_model=list[ChargeSheetOut])
def sheets_for_a_selection(
    freight_ids: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
    _=ReadDep,
):
    """The sheets for freights about to be invoiced.

    The invoice preview lets the office tick individual freights. This answers
    with the sheets for exactly that tick list, so what the vendor will be
    sent is visible before the invoice exists.
    """
    return [_out(s) for s in sheets_for_freights(db, freight_ids)]
