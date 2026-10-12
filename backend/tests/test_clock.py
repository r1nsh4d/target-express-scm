"""Comparing a stored timestamp with now.

This exists because of a bug the rest of the suite could not see.

Every timestamp column here is `DateTime(timezone=True)`. Postgres stores
timestamptz and psycopg returns timezone-AWARE datetimes; `datetime.now()` is
naive; Python refuses to compare the two and raises TypeError. The result was a
freight that listed perfectly and whose detail page said "Trip not found", and
a customer tracking link that could never have worked.

The tests did not catch it because they run on SQLite, which has no timestamptz
and hands back naive datetimes for the same column — so the comparison worked
everywhere it was tested and failed everywhere it mattered.

So these tests pass BOTH kinds in explicitly, rather than relying on whatever
the database of the day happens to return.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.clock import has_passed, is_future, now_like

IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------------
# The case that broke production
# ---------------------------------------------------------------------------


def test_an_aware_future_time_does_not_raise():
    """The exact comparison that 500'd the freight detail page."""
    assert is_future(datetime.now(timezone.utc) + timedelta(days=3)) is True


def test_an_aware_past_time_does_not_raise():
    assert has_passed(datetime.now(timezone.utc) - timedelta(hours=1)) is True


def test_a_naive_time_still_works():
    """SQLite, and anything that stores plain timestamps."""
    assert is_future(datetime.now() + timedelta(days=3)) is True
    assert has_passed(datetime.now() - timedelta(hours=1)) is True


@pytest.mark.parametrize("tz", [None, timezone.utc, IST, timezone(timedelta(hours=-5))])
def test_every_kind_of_timestamp_compares(tz):
    """Naive, UTC, Indian, and somewhere across the date line — a tracking link
    must behave the same for all of them."""
    now = datetime.now(tz) if tz else datetime.now()

    assert is_future(now + timedelta(minutes=5)) is True
    assert has_passed(now + timedelta(minutes=5)) is False
    assert is_future(now - timedelta(minutes=5)) is False
    assert has_passed(now - timedelta(minutes=5)) is True


def test_the_offset_is_respected_not_ignored():
    """Stripping tzinfo would make this pass by accident. 23:00 IST is still
    ahead of now in UTC terms, and an hour from now in UTC is still ahead when
    written as IST."""
    an_hour_off = datetime.now(timezone.utc) + timedelta(hours=1)
    assert is_future(an_hour_off.astimezone(IST)) is True

    an_hour_ago = datetime.now(IST) - timedelta(hours=1)
    assert has_passed(an_hour_ago.astimezone(timezone.utc)) is True


# ---------------------------------------------------------------------------
# Nothing recorded
# ---------------------------------------------------------------------------


def test_a_missing_timestamp_has_not_passed():
    """A record with no expiry has not expired. Treating a missing timestamp as
    "already happened" is how a live tracking link gets refused."""
    assert has_passed(None) is False


def test_a_missing_timestamp_is_not_in_the_future_either():
    assert is_future(None) is False


# ---------------------------------------------------------------------------
# The helper underneath
# ---------------------------------------------------------------------------


def test_now_matches_what_it_is_compared_with():
    assert now_like(datetime.now()).tzinfo is None
    assert now_like(datetime.now(timezone.utc)).tzinfo is timezone.utc
    assert now_like(datetime.now(IST)).tzinfo is IST
