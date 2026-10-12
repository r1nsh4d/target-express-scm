"""Comparing a stored time with now, without caring which kind it is.

Every timestamp column in this schema is `DateTime(timezone=True)`, so Postgres
stores timestamptz and psycopg hands them back timezone-AWARE. `datetime.now()`
is naive. Python refuses to compare the two:

    TypeError: can't compare offset-naive and offset-aware datetimes

which surfaces as a 500 — and in the case that prompted this, as a freight that
listed perfectly well and whose detail page said "Trip not found".

It never showed up in the tests because they run on SQLite, which has no
timestamptz and returns naive datetimes for the same column. So the comparison
worked everywhere it was tested and failed everywhere it mattered. That is
precisely why this is one named function with its own tests rather than a
`datetime.now()` written out at each call site: the next person to compare a
timestamp should not have to know any of the above.
"""

from __future__ import annotations

from datetime import datetime


def now_like(moment: datetime) -> datetime:
    """The current time, in whichever form `moment` is in.

    Aware in, aware out — in the same timezone, so the comparison is a real
    one rather than a coincidence of offsets.
    """
    return datetime.now(moment.tzinfo) if moment.tzinfo is not None else datetime.now()


def has_passed(moment: datetime | None) -> bool:
    """Is this moment behind us?

    None is not in the past. A record with no expiry has not expired, and
    treating a missing timestamp as "already happened" is how a live tracking
    link gets refused.
    """
    if moment is None:
        return False
    return moment <= now_like(moment)


def is_future(moment: datetime | None) -> bool:
    """Is this moment still ahead of us? None is not."""
    if moment is None:
        return False
    return moment > now_like(moment)
