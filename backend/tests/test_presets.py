"""Route presets — the saved rounds, and the rules that keep them honest.

Two properties matter more than anything else here:

  1. Sequence is assigned by the server, never accepted from the client. A gap
     or a duplicate in what was posted must not become a gap or duplicate in the
     round, because the stop order IS the route the driver follows.

  2. The same customer cannot appear twice. Silently deduplicating would change
     the billable point count on every freight built from the preset, and the
     vendor is charged per point beyond those included.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.api.routes.presets import MarketVehicleIn, PresetIn, PresetPointIn
from app.models.enums import MarketVehicleStanding


def _point(**kw) -> PresetPointIn:
    return PresetPointIn(consignee_id=str(uuid.uuid4()), **kw)


# ---------------------------------------------------------------------------
# Preset validation
# ---------------------------------------------------------------------------


def test_a_route_needs_a_name():
    with pytest.raises(ValidationError):
        PresetIn(name="")


def test_the_office_s_own_names_are_kept_verbatim():
    """"No. 11" is what they call it. It is not ours to tidy into "Route 11"."""
    assert PresetIn(name="  No. 11  ").name == "No. 11"
    assert PresetIn(name="Kasaragod Tuesday").name == "Kasaragod Tuesday"


def test_the_same_customer_twice_is_rejected_not_deduplicated():
    """Deduplicating silently would change what the vendor is billed.

    Points beyond those included are charged per point, so a preset that
    quietly dropped a stop would under-bill every freight built from it.
    """
    same = str(uuid.uuid4())
    with pytest.raises(ValidationError) as exc:
        PresetIn(
            name="No. 11",
            points=[
                PresetPointIn(consignee_id=same),
                PresetPointIn(consignee_id=same),
            ],
        )
    assert "twice" in str(exc.value)


def test_different_customers_are_fine():
    preset = PresetIn(name="No. 11", points=[_point(), _point(), _point()])
    assert len(preset.points) == 3


def test_a_route_may_start_empty():
    """You name the round first, then add the stops as you remember them."""
    assert PresetIn(name="No. 11").points == []


def test_floor_defaults_are_bounded():
    """Floor count is a billable fact for furniture, so a typo is money."""
    with pytest.raises(ValidationError):
        _point(default_floor_number=-1)
    with pytest.raises(ValidationError):
        _point(default_floor_number=100)

    assert _point(default_floor_number=3).default_floor_number == 3


def test_a_stop_carries_its_standing_facts():
    """A third-floor shop with no lift is that every week. Nobody retypes it."""
    stop = _point(default_floor_number=3, default_has_lift=False, delivery_hint="Ask for Shaji")
    assert stop.default_floor_number == 3
    assert stop.default_has_lift is False
    assert stop.delivery_hint == "Ask for Shaji"


def test_typical_km_is_bounded():
    with pytest.raises(ValidationError):
        PresetIn(name="No. 11", typical_round_trip_km=-5)
    assert PresetIn(name="No. 11", typical_round_trip_km=900).typical_round_trip_km == 900


# ---------------------------------------------------------------------------
# Market vehicle phonebook
# ---------------------------------------------------------------------------


def test_registration_is_normalised_for_searching():
    """Typed as 'kl 07 aa 1234', searched as 'KL07AA1234'."""
    assert MarketVehicleIn(
        contact_name="Shaji", phone="9847012345", registration_no="kl 07 aa 1234"
    ).registration_no == "KL07AA1234"


def test_a_contact_without_a_lorry_is_valid():
    """A broker supplies whatever is free that day. The registration is often
    not known until the lorry is already on its way."""
    row = MarketVehicleIn(contact_name="Shaji Transports", phone="9847012345")
    assert row.registration_no is None
    assert row.vehicle_type_id is None


def test_a_blank_registration_becomes_none_not_empty_string():
    assert MarketVehicleIn(contact_name="Shaji", phone="9847012345", registration_no="   ").registration_no is None


def test_a_new_contact_starts_untried():
    """Nobody is reliable until they have actually turned up."""
    assert MarketVehicleIn(contact_name="Shaji", phone="9847012345").standing == (
        MarketVehicleStanding.UNTRIED
    )


def test_a_negative_rate_is_refused():
    with pytest.raises(ValidationError):
        MarketVehicleIn(contact_name="Shaji", phone="9847012345", last_hired_rate=-1)


def test_contact_needs_a_phone_long_enough_to_dial():
    with pytest.raises(ValidationError):
        MarketVehicleIn(contact_name="Shaji", phone="99")


def test_standing_has_exactly_three_states():
    """Three, not a star rating. The question at 7am is 'can I call this one'."""
    assert set(MarketVehicleStanding) == {
        MarketVehicleStanding.UNTRIED,
        MarketVehicleStanding.RELIABLE,
        MarketVehicleStanding.AVOID,
    }
