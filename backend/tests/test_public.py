"""The public endpoints, which the whole internet can reach.

The tracking lookup is the one that matters. An LR number is a sequence: if a
bare reference were enough, anyone could walk 0001 upward and read every
customer, address and phone number the company holds. So the tests below are
mostly about what the endpoint REFUSES, and about the fact that every refusal
looks the same from outside.
"""

import re
import time

import pytest
from fastapi import HTTPException, Request

from app.api.routes.public import (
    LOOKUP_FAILED,
    EnquiryIn,
    TrackLookupIn,
    _digits,
    _hits,
    _rate_limit,
)


def _request(ip: str = "198.51.100.7") -> Request:
    """A Request with just enough scope for the rate limiter to read a client."""
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/public/enquiries",
            "headers": [],
            "client": (ip, 54321),
        }
    )


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    _hits.clear()
    yield
    _hits.clear()


# ---------------------------------------------------------------------------
# Phone comparison
# ---------------------------------------------------------------------------


def test_phone_digits_ignore_formatting():
    """One person, five ways of writing their number, one comparison key."""
    assert (
        _digits("+91 98470 12345")
        == _digits("09847012345")
        == _digits("98470-12345")
        == _digits("(+91) 9847012345")
        == "9847012345"
    )


def test_phone_digits_tolerate_a_country_code_on_one_side_only():
    assert _digits("+919847012345") == _digits("9847012345")


def test_phone_digits_do_not_collapse_different_numbers():
    assert _digits("9847012345") != _digits("9847012346")


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limit_allows_up_to_the_limit_then_refuses():
    request = _request()
    for _ in range(3):
        _rate_limit(request, "t", limit=3, per_seconds=60)

    with pytest.raises(HTTPException) as exc:
        _rate_limit(request, "t", limit=3, per_seconds=60)
    assert exc.value.status_code == 429


def test_rate_limit_is_per_client():
    """One abusive address must not lock out everyone else."""
    for _ in range(3):
        _rate_limit(_request("203.0.113.1"), "t", limit=3, per_seconds=60)

    # A different address still gets its full allowance.
    _rate_limit(_request("203.0.113.2"), "t", limit=3, per_seconds=60)


def test_rate_limit_window_expires():
    request = _request()
    _rate_limit(request, "t", limit=1, per_seconds=60)

    with pytest.raises(HTTPException):
        _rate_limit(request, "t", limit=1, per_seconds=60)

    # Age the recorded hit past the window rather than sleeping for a minute.
    key = next(iter(_hits))
    _hits[key][0] = time.monotonic() - 61
    _rate_limit(request, "t", limit=1, per_seconds=60)


def test_rate_limit_buckets_are_independent():
    """Hammering the enquiry form must not lock the person out of tracking."""
    request = _request()
    for _ in range(3):
        _rate_limit(request, "enquiry", limit=3, per_seconds=60)
    _rate_limit(request, "track", limit=3, per_seconds=60)


# ---------------------------------------------------------------------------
# The failure message
# ---------------------------------------------------------------------------


def test_failure_message_names_no_reason():
    """A wrong phone, an unknown LR and an undispatched freight share one
    message. Anything that distinguishes them turns this into an oracle for
    which LR numbers exist."""
    lowered = LOOKUP_FAILED.lower()
    for leak in ("not dispatched", "wrong phone", "does not exist", "no such", "expired"):
        assert leak not in lowered


# ---------------------------------------------------------------------------
# Enquiry validation
# ---------------------------------------------------------------------------


def test_enquiry_requires_a_callable_number():
    with pytest.raises(ValueError):
        EnquiryIn(company_name="Acme Traders", contact_name="Rahul", phone="----")


def test_enquiry_accepts_an_indian_mobile():
    enquiry = EnquiryIn(
        company_name="Acme Traders",
        contact_name="Rahul",
        phone="+91 98470 12345",
    )
    assert enquiry.email is None


def test_enquiry_blank_email_becomes_none_not_empty_string():
    enquiry = EnquiryIn(
        company_name="Acme Traders",
        contact_name="Rahul",
        phone="9847012345",
        email="   ",
    )
    assert enquiry.email is None


def test_enquiry_rejects_a_malformed_email():
    with pytest.raises(ValueError):
        EnquiryIn(
            company_name="Acme Traders",
            contact_name="Rahul",
            phone="9847012345",
            email="rahul@acme",
        )


def test_enquiry_message_is_length_bounded():
    """Every field here is attacker-supplied."""
    with pytest.raises(ValueError):
        EnquiryIn(
            company_name="Acme Traders",
            contact_name="Rahul",
            phone="9847012345",
            message="x" * 2001,
        )


def test_enquiry_honeypot_field_exists_and_is_optional():
    """Bots fill every field they find. Real people never see this one."""
    clean = EnquiryIn(company_name="Acme Traders", contact_name="Rahul", phone="9847012345")
    assert clean.website is None

    bot = EnquiryIn(
        company_name="Acme Traders",
        contact_name="Rahul",
        phone="9847012345",
        website="http://spam.example",
    )
    assert bot.website


# ---------------------------------------------------------------------------
# Lookup input
# ---------------------------------------------------------------------------


def test_lookup_reference_is_upper_cased_and_trimmed():
    """People type what is printed, with whatever spacing and case."""
    payload = TrackLookupIn(reference="  tx-lr-0042 ", phone="9847012345")
    assert payload.reference == "TX-LR-0042"


def test_lookup_rejects_a_reference_too_short_to_be_real():
    with pytest.raises(ValueError):
        TrackLookupIn(reference="7", phone="9847012345")


def test_lookup_requires_a_phone():
    with pytest.raises(ValueError):
        TrackLookupIn(reference="TX-LR-0042", phone="")


def test_lookup_link_lifetime_is_short():
    """A link handed out on a phone-number check is not a link that was sent to
    a verified address. One day, not thirty."""
    from app.api.routes.public import LOOKUP_LINK_HOURS

    assert 0 < LOOKUP_LINK_HOURS <= 48


def test_issued_tokens_are_not_guessable():
    """The token IS the credential for the tracking page."""
    import secrets

    token = secrets.token_urlsafe(24)
    assert len(token) >= 32
    assert re.fullmatch(r"[A-Za-z0-9_-]+", token)
