"""A link that lets a customer fill in their own delivery details.

The warehouse admin entering a morning's bills types a name, a mobile and a
town. That is what he has and all he has time for, and asking him for more at
that moment is how a day sheet stops getting used. Everything else — the
door, the landmark, the floor, the pin — belongs to the person who lives
there, and the only practical way to ask them is to send a link.

WHAT IT IS AND IS NOT

The token reaches exactly one consignee and grants nothing else. It is a link
to correct your own delivery address, not a login: there is no password to
leak, no other record behind it, and it expires. The same shape as the
tracking link, for the same reason — the people using it will not install
anything and should not have to.

WHAT IT SETS, AND WHAT IT CANNOT

The customer sets their own address, landmark, floor, pin and who to ask for.
They cannot change their name, because the name is what the vendor's bill says
and a mismatch between the two is how a consignment becomes untraceable. They
cannot change their phone either — the link was sent to it, so a link that can
move itself to another number is a link that can be stolen in one hop.

THE PIN IS MARKED VERIFIED. Somebody standing at the address put it there,
which is a better source than anything the office could type.

SENDING IT IS SOMEBODY ELSE'S JOB. This mints the link and records that it was
asked for; which WhatsApp number it goes out from is configuration, and until
that is set the office copies the link and sends it by hand. That is a worse
experience and a working one, which is the right order to build them in.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_capability
from app.core.config import settings
from app.core.privileges import Capability
from app.db.session import get_db
from app.models.consignee import Consignee
from app.models.enums import ConsigneeType, GeoConfidence

router = APIRouter(prefix="/api", tags=["customer link"])

# Long enough that it cannot be guessed, short enough to survive being pasted
# into WhatsApp by somebody who is not concentrating.
TOKEN_DAYS = 30


class LinkOut(BaseModel):
    """What the office needs in order to send it."""

    url: str
    expires_at: datetime
    requested_at: datetime
    completed_at: datetime | None
    customer_name: str
    phone: str | None
    # Ready-made, because the office sending this is doing it forty times a
    # morning and should not be composing a sentence each time.
    whatsapp_text: str


def _mint(consignee: Consignee) -> None:
    consignee.details_token = secrets.token_urlsafe(24)
    consignee.details_token_expires_at = datetime.now().astimezone() + timedelta(
        days=TOKEN_DAYS
    )
    consignee.details_requested_at = datetime.now().astimezone()
    consignee.details_completed_at = None


def _out(consignee: Consignee) -> LinkOut:
    base = (settings.public_base_url or "").rstrip("/")
    url = f"{base}/my-details/{consignee.details_token}"
    return LinkOut(
        url=url,
        expires_at=consignee.details_token_expires_at,
        requested_at=consignee.details_requested_at,
        completed_at=consignee.details_completed_at,
        customer_name=consignee.name,
        phone=consignee.phone,
        whatsapp_text=(
            f"Hello {consignee.name}, this is {settings.company_name or 'Target Express'}. "
            "We are delivering to you shortly. Please confirm your address and drop a pin "
            f"so our driver finds you first time: {url}"
        ),
    )


@router.post("/consignees/{consignee_id}/details-link", response_model=LinkOut)
def request_details(
    consignee_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_capability(Capability.FLEET)),
):
    """Mint a link for this customer to complete their own record.

    Minting again replaces the old one, which is what somebody means when
    they press it a second time: the first link went to a wrong number, or
    was never opened, and the one they are about to send should be the only
    one that works.
    """
    consignee = db.get(Consignee, consignee_id)
    if consignee is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    _mint(consignee)
    db.commit()
    db.refresh(consignee)
    return _out(consignee)


@router.get("/consignees/{consignee_id}/details-link", response_model=LinkOut)
def current_link(
    consignee_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_capability(Capability.FLEET)),
):
    """The link already sent, so it can be sent again without a new one.

    Re-minting on every look would invalidate the link the customer is
    holding, which is exactly the one the office is trying to chase up.
    """
    consignee = db.get(Consignee, consignee_id)
    if consignee is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not consignee.details_token:
        raise HTTPException(status_code=404, detail="No link has been sent to this customer")
    return _out(consignee)


# --------------------------------------------------------------------------- #
# The customer's own page. No login — the token is the whole credential.      #
# --------------------------------------------------------------------------- #


class MyDetailsOut(BaseModel):
    """What the customer is shown about themselves.

    Deliberately thin. Nothing about the vendor, the trip, the driver or any
    other customer appears here — the token proves one thing, and this is the
    one thing it proves.
    """

    name: str
    type: str
    phone: str | None
    contact_person: str | None
    address: str | None
    city: str | None
    pincode: str | None
    landmark: str | None
    delivery_notes: str | None
    latitude: float | None
    longitude: float | None
    already_completed: bool
    company_name: str


class MyDetailsIn(BaseModel):
    # Not the name and not the phone. The name has to match the vendor's bill,
    # and a link that can move itself to another number is a link that is
    # stolen in one hop.
    contact_person: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=10)
    landmark: str | None = Field(default=None, max_length=500)
    delivery_notes: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    alternate_phone: str | None = Field(default=None, max_length=20)


def _by_token(db: Session, token: str) -> Consignee:
    consignee = db.execute(
        select(Consignee).where(Consignee.details_token == token)
    ).scalars().first()

    if consignee is None or not consignee.is_active:
        raise HTTPException(status_code=404, detail="This link is no longer active")

    expires = consignee.details_token_expires_at
    if expires is not None:
        now = datetime.now(expires.tzinfo) if expires.tzinfo else datetime.now()
        if expires < now:
            raise HTTPException(
                status_code=404,
                detail="This link has expired. Ask us to send you a new one.",
            )
    return consignee


@router.get("/my-details/{token}", response_model=MyDetailsOut)
def my_details(token: str, db: Session = Depends(get_db)):
    consignee = _by_token(db, token)
    return MyDetailsOut(
        name=consignee.name,
        type=str(consignee.type),
        phone=consignee.phone,
        contact_person=consignee.contact_person,
        address=consignee.address,
        city=consignee.city,
        pincode=consignee.pincode,
        landmark=consignee.landmark,
        delivery_notes=consignee.delivery_notes,
        latitude=float(consignee.latitude) if consignee.latitude is not None else None,
        longitude=float(consignee.longitude) if consignee.longitude is not None else None,
        already_completed=consignee.details_completed_at is not None,
        company_name=settings.company_name or "Target Express",
    )


@router.post("/my-details/{token}", response_model=MyDetailsOut)
def save_my_details(token: str, payload: MyDetailsIn, db: Session = Depends(get_db)):
    """What the customer says about their own address.

    The link stays live after this. People remember the landmark an hour
    later, or move, and burning the token on first use turns a correction
    into a phone call.
    """
    consignee = _by_token(db, token)

    data = payload.model_dump(exclude_unset=True)
    for field in (
        "contact_person",
        "address",
        "city",
        "pincode",
        "landmark",
        "delivery_notes",
        "alternate_phone",
    ):
        if field in data:
            value = (data[field] or "").strip()
            setattr(consignee, field, value or None)

    if data.get("latitude") is not None and data.get("longitude") is not None:
        consignee.latitude = data["latitude"]
        consignee.longitude = data["longitude"]
        # Somebody standing at the address put it there, which beats anything
        # the office could type from a town name.
        consignee.geo_confidence = GeoConfidence.VERIFIED

    consignee.details_completed_at = datetime.now().astimezone()
    db.commit()
    db.refresh(consignee)
    return my_details(token, db)


class WaitingOut(BaseModel):
    """A customer whose record is still a name and a town.

    Worth a list of its own. These are the deliveries that will go wrong, and
    they are invisible on a customer screen sorted by name.
    """

    id: str
    name: str
    type: str
    phone: str | None
    city: str | None
    has_address: bool
    has_pin: bool
    link_sent_at: datetime | None
    completed_at: datetime | None


@router.get("/consignees-incomplete", response_model=list[WaitingOut])
def incomplete(
    db: Session = Depends(get_db),
    _=Depends(require_capability(Capability.FLEET)),
):
    """Customers missing an address or a pin, newest first."""
    rows = (
        db.execute(
            select(Consignee)
            .where(
                Consignee.is_active.is_(True),
                (Consignee.address.is_(None)) | (Consignee.latitude.is_(None)),
            )
            .order_by(Consignee.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        WaitingOut(
            id=str(c.id),
            name=c.name,
            type=str(c.type),
            phone=c.phone,
            city=c.city,
            has_address=bool(c.address),
            has_pin=c.latitude is not None,
            link_sent_at=c.details_requested_at,
            completed_at=c.details_completed_at,
        )
        for c in rows
    ]


__all__ = ["router", "ConsigneeType"]
