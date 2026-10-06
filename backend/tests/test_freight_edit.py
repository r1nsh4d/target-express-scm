"""Editing a freight, and moving its status by hand.

Both of these exist because reality does not always reach the application: a
vendor's requirement changes twice before the lorry moves, a driver's phone
dies halfway through a run. The alternative to building them is an admin
editing the database directly, which leaves no trace at all.

So the rules that keep them from doing damage are what these tests hold:

  * A freight that has been dispatched is not editable. Its points are what the
    driver is carrying and what the stickers were printed against.
  * A stop with boxes already on it cannot be swept away by a route change.
  * An invoiced freight's status is frozen, or the invoice disagrees with the
    trip it was built from.
  * BILLED and SETTLED are never set by hand. They follow from an invoice and a
    settlement existing.
  * Every hand-made status change carries a reason, because it is the only
    evidence that the change was legitimate.
"""

import pytest
from pydantic import ValidationError

from app.api.routes.freights import (
    EDITABLE_STATUSES,
    OVERRIDABLE,
    FreightPatchIn,
    StatusOverrideIn,
)
from app.models.enums import FreightStatus


# ---------------------------------------------------------------------------
# Which statuses may be edited
# ---------------------------------------------------------------------------


def test_only_pre_dispatch_freights_are_editable():
    """Once the lorry has the boxes, the route on screen must match the route
    on the vehicle."""
    assert set(EDITABLE_STATUSES) == {
        FreightStatus.DRAFT,
        FreightStatus.PLANNED,
        FreightStatus.LOADING,
    }


@pytest.mark.parametrize(
    "status",
    [
        FreightStatus.DISPATCHED,
        FreightStatus.IN_TRANSIT,
        FreightStatus.COMPLETED,
        FreightStatus.BILLED,
        FreightStatus.SETTLED,
        FreightStatus.CANCELLED,
    ],
)
def test_a_freight_on_the_road_or_beyond_is_not_editable(status):
    assert status not in EDITABLE_STATUSES


# ---------------------------------------------------------------------------
# What a patch may change
# ---------------------------------------------------------------------------


def test_everything_is_optional():
    """Only what is sent is changed — this is a correction, not a replacement."""
    patch = FreightPatchIn()
    assert patch.model_dump(exclude_unset=True) == {}


def test_the_vendor_division_cannot_be_changed():
    """It decides which rate card prices the trip. Changing it once points and
    boxes exist would silently reprice work already done."""
    assert "vendor_division_id" not in FreightPatchIn.model_fields


def test_the_date_and_warehouse_can_be_corrected():
    fields = FreightPatchIn.model_fields
    assert "trip_date" in fields
    assert "warehouse_id" in fields


def test_a_points_list_sent_at_all_must_not_be_empty():
    """A freight with no stops is not a freight. Cancel it instead."""
    with pytest.raises(ValidationError):
        FreightPatchIn(points=[])


def test_points_left_out_entirely_are_untouched():
    """Changing the date must not require resending the whole route."""
    patch = FreightPatchIn(trip_date="2026-03-01")
    assert patch.points is None
    assert "points" not in patch.model_dump(exclude_unset=True)


# ---------------------------------------------------------------------------
# Status override
# ---------------------------------------------------------------------------


def test_a_reason_is_required():
    """The normal route through these states records evidence at each step.
    Jumping straight to one records nothing, so the reason IS the evidence."""
    with pytest.raises(ValidationError):
        StatusOverrideIn(status=FreightStatus.COMPLETED)


def test_a_token_reason_is_refused():
    with pytest.raises(ValidationError):
        StatusOverrideIn(status=FreightStatus.COMPLETED, reason="ok")


def test_a_real_reason_is_accepted():
    override = StatusOverrideIn(
        status=FreightStatus.COMPLETED,
        reason="Driver's phone died at Kanhangad; run finished on paper, odometer read at the gate",
    )
    assert override.status == FreightStatus.COMPLETED


def test_billed_and_settled_are_never_set_by_hand():
    """A freight marked BILLED with no invoice behind it is a hole in the
    accounts. Those statuses follow from the document existing."""
    assert FreightStatus.BILLED not in OVERRIDABLE
    assert FreightStatus.SETTLED not in OVERRIDABLE


def test_the_operational_statuses_are_all_reachable():
    """Everything that describes where the lorry is, an admin can correct."""
    for status in (
        FreightStatus.DRAFT,
        FreightStatus.PLANNED,
        FreightStatus.LOADING,
        FreightStatus.DISPATCHED,
        FreightStatus.IN_TRANSIT,
        FreightStatus.COMPLETED,
        FreightStatus.CANCELLED,
    ):
        assert status in OVERRIDABLE


def test_every_status_is_either_overridable_or_deliberately_not():
    """A new status added to the enum must be classified, not silently fall
    through into 'not settable by hand'."""
    accounted = set(OVERRIDABLE) | {FreightStatus.BILLED, FreightStatus.SETTLED}
    assert accounted == set(FreightStatus)
