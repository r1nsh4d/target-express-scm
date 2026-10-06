"""Everything the public internet is allowed to reach, in one file.

Two jobs:

  1. Business enquiries from the landing page.
  2. "Where is my delivery?" — finding a tracking link from a number the
     customer actually has, instead of needing the SMS they deleted.

Both are unauthenticated, so both are written defensively. The rules this module
holds to:

  * A lookup needs TWO facts: the document number AND the phone it was booked
    against. A bare LR number is a sequence — anyone could walk it from 0001 and
    read the whole book. The phone is the shared secret.
  * Failure is always the same message and always the same shape, whether the
    document does not exist, the phone does not match, or the freight has not
    been dispatched. Anything else turns this endpoint into an oracle for which
    LR numbers are real.
  * Both endpoints are rate limited per IP, because neither is worth anything
    to an attacker who can only try a handful of times.
"""

from __future__ import annotations

import re
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_ROLES, get_current_user, require_roles
from app.db.session import get_db
from app.models.consignee import Consignee
from app.models.consignment import Consignment
from app.models.enquiry import Enquiry
from app.models.enums import EnquiryStatus, FreightStatus
from app.models.freight import Freight, FreightPoint
from app.models.tracking import TrackingSession
from app.models.user import User
from app.schemas.base import ORMModel

router = APIRouter(prefix="/api/public", tags=["public"])

# How long a link found this way stays good. Short: it was handed out to
# somebody who proved they had the phone number a minute ago, not sent to a
# verified address.
LOOKUP_LINK_HOURS = 24

# The one message every failed lookup returns. Deliberately identical for a
# wrong number, an unknown number and an undispatched freight.
LOOKUP_FAILED = (
    "We could not find a delivery for that number and phone. Check the LR or "
    "bill number on your invoice, and the phone number given at booking."
)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

# In-process and per-worker, which is the right size for this: the app runs as
# one container, and the cost of a miss is a few extra attempts, not a breach.
# If this ever runs multi-worker behind a load balancer, move it to Redis.
_hits: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(request: Request, bucket: str, limit: int, per_seconds: int) -> None:
    client = request.client.host if request.client else "unknown"
    key = f"{bucket}:{client}"
    now = time.monotonic()
    window = _hits[key]

    while window and now - window[0] > per_seconds:
        window.popleft()

    if len(window) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait a minute and try again.",
        )

    window.append(now)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _digits(value: str) -> str:
    """Compare phone numbers by their digits only.

    People type +91 98470 12345, 098470-12345 and 9847012345 for the same phone.
    Only the last ten digits are compared, so a country code on one side and not
    the other does not cause a false miss.
    """
    return re.sub(r"\D", "", value or "")[-10:]


# ---------------------------------------------------------------------------
# Enquiries
# ---------------------------------------------------------------------------


class EnquiryIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=6, max_length=20)
    email: str | None = Field(default=None, max_length=200)

    goods_type: str | None = Field(default=None, max_length=120)
    origin_city: str | None = Field(default=None, max_length=120)
    monthly_volume: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=2000)

    # A honeypot. Real people never see this field, so anything in it is a bot.
    # Accepted and silently discarded rather than rejected — a bot that gets a
    # 422 learns to try again without it.
    website: str | None = Field(default=None, max_length=200)

    @field_validator("phone")
    @classmethod
    def _phone_has_digits(cls, value: str) -> str:
        if len(re.sub(r"\D", "", value)) < 6:
            raise ValueError("Enter a phone number we can call you back on")
        return value.strip()

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", value):
            raise ValueError("That email address does not look right")
        return value


class EnquiryAck(BaseModel):
    ok: bool = True
    message: str


@router.post("/enquiries", response_model=EnquiryAck, status_code=status.HTTP_201_CREATED)
def submit_enquiry(
    payload: EnquiryIn,
    request: Request,
    db: Session = Depends(get_db),
) -> EnquiryAck:
    """A business asking to work with Target Express."""
    _rate_limit(request, "enquiry", limit=5, per_seconds=600)

    enquiry = Enquiry(
        company_name=payload.company_name.strip(),
        contact_name=payload.contact_name.strip(),
        phone=payload.phone.strip(),
        email=payload.email,
        goods_type=(payload.goods_type or "").strip() or None,
        origin_city=(payload.origin_city or "").strip() or None,
        monthly_volume=(payload.monthly_volume or "").strip() or None,
        message=(payload.message or "").strip() or None,
        source_ip=_client_ip(request),
        # Filled honeypot: stored, flagged, and kept out of the office's list.
        is_spam=bool(payload.website and payload.website.strip()),
    )
    if enquiry.is_spam:
        enquiry.status = EnquiryStatus.SPAM

    db.add(enquiry)
    db.commit()

    # The same acknowledgement either way. A bot is told it succeeded.
    return EnquiryAck(
        message=(
            "Thank you. Your enquiry has reached our operations desk and "
            "someone will call you within one working day."
        )
    )


# ---------------------------------------------------------------------------
# Find my delivery
# ---------------------------------------------------------------------------


class TrackLookupIn(BaseModel):
    """The two things a consignee has in their hand."""

    reference: str = Field(min_length=3, max_length=64)
    phone: str = Field(min_length=6, max_length=20)

    @field_validator("reference")
    @classmethod
    def _clean_reference(cls, value: str) -> str:
        return value.strip().upper()


class TrackLookupOut(BaseModel):
    token: str


def _issue_token(db: Session, point: FreightPoint) -> str:
    """Reuse a live tracking link if one exists, otherwise mint a short one.

    Reusing matters: the customer may already have this link in a WhatsApp
    message, and two live links for one delivery is two things to revoke.
    """
    existing = (
        db.execute(
            select(TrackingSession)
            .where(
                TrackingSession.freight_point_id == point.id,
                TrackingSession.is_active.is_(True),
                TrackingSession.expires_at > datetime.now(),
            )
            .order_by(TrackingSession.expires_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing.token

    session = TrackingSession(
        freight_point_id=point.id,
        token=secrets.token_urlsafe(24),
        expires_at=datetime.now() + timedelta(hours=LOOKUP_LINK_HOURS),
    )
    db.add(session)
    db.flush()
    return session.token


@router.post("/track/lookup", response_model=TrackLookupOut)
def lookup_tracking(
    payload: TrackLookupIn,
    request: Request,
    db: Session = Depends(get_db),
) -> TrackLookupOut:
    """Exchange an LR or bill number plus a phone for a tracking link.

    The reference is whatever is printed on the paper the customer is holding:
    the LR number, the freight number, or the vendor's own bill number.
    """
    _rate_limit(request, "track", limit=12, per_seconds=300)

    reference = payload.reference
    phone = _digits(payload.phone)
    if len(phone) < 6:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=LOOKUP_FAILED)

    # Candidate points: everything the reference could be pointing at. The
    # phone check below is what narrows it to one.
    candidates: list[FreightPoint] = []

    freights = (
        db.execute(
            select(Freight).where(
                or_(
                    func.upper(Freight.lr_no) == reference,
                    func.upper(Freight.trip_no) == reference,
                )
            )
        )
        .scalars()
        .all()
    )
    for freight in freights:
        candidates.extend(freight.points)

    consignments = (
        db.execute(
            select(Consignment).where(
                func.upper(Consignment.vendor_bill_no) == reference,
                Consignment.freight_point_id.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    for consignment in consignments:
        point = db.get(FreightPoint, consignment.freight_point_id)
        if point is not None:
            candidates.append(point)

    for point in candidates:
        consignee: Consignee | None = point.consignee
        if consignee is None:
            continue

        # The consignee's own number or their alternate. Either is proof enough
        # that this is their parcel.
        known = {_digits(p) for p in (consignee.phone, consignee.alternate_phone) if p}
        if phone not in known:
            continue

        # Nothing to show before the run leaves the warehouse, and saying so
        # would confirm the LR exists. Same failure as an unknown number.
        if point.freight.status in (FreightStatus.DRAFT, FreightStatus.PLANNED):
            continue

        token = _issue_token(db, point)
        db.commit()
        return TrackLookupOut(token=token)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=LOOKUP_FAILED)


# ---------------------------------------------------------------------------
# The office's side of the enquiry list
# ---------------------------------------------------------------------------

admin_router = APIRouter(
    prefix="/api/enquiries",
    tags=["enquiries"],
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
)


class EnquiryOut(ORMModel):
    id: str
    company_name: str
    contact_name: str
    phone: str
    email: str | None
    goods_type: str | None
    origin_city: str | None
    monthly_volume: str | None
    message: str | None
    status: EnquiryStatus
    internal_note: str | None
    contacted_at: datetime | None
    created_at: datetime


class EnquiryUpdate(BaseModel):
    status: EnquiryStatus | None = None
    internal_note: str | None = Field(default=None, max_length=2000)


@admin_router.get("", response_model=list[EnquiryOut])
def list_enquiries(
    status_filter: EnquiryStatus | None = None,
    include_spam: bool = False,
    db: Session = Depends(get_db),
) -> list[Enquiry]:
    """Newest first — an enquiry two days old is already cold.

    The id is a tiebreaker, not decoration. Two enquiries arriving in the same
    second would otherwise come back in whatever order the database felt like,
    so the list would quietly reshuffle every time the office refreshed it.
    A uuid4 order is arbitrary, but it is STABLE, which is the property that
    matters here.
    """
    stmt = (
        select(Enquiry)
        .order_by(Enquiry.created_at.desc(), Enquiry.id.desc())
        .limit(500)
    )
    if status_filter is not None:
        stmt = stmt.where(Enquiry.status == status_filter)
    elif not include_spam:
        stmt = stmt.where(Enquiry.is_spam.is_(False))
    return list(db.execute(stmt).scalars().all())


@admin_router.patch("/{enquiry_id}", response_model=EnquiryOut)
def update_enquiry(
    enquiry_id: uuid.UUID,
    payload: EnquiryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Enquiry:
    enquiry = db.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    if payload.status is not None:
        # The first move off NEW is the one worth timestamping: it is the
        # answer to "did anyone actually call them back, and when".
        if enquiry.status == EnquiryStatus.NEW and payload.status != EnquiryStatus.NEW:
            enquiry.contacted_at = datetime.now()
        enquiry.status = payload.status
        enquiry.is_spam = payload.status == EnquiryStatus.SPAM
        enquiry.assigned_to_id = user.id

    if payload.internal_note is not None:
        enquiry.internal_note = payload.internal_note.strip() or None

    db.commit()
    db.refresh(enquiry)
    return enquiry
