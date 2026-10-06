"""Coolie charges — a separate head, not more unloading.

At some markets and godowns a local porter gang controls who is allowed to
unload. They are not Target Express's crew and not on the unloading rate sheet.
The driver pays them in cash at the point and the vendor reimburses it.

The whole reason this is its own head rather than another unloading number is
answerability: when a vendor asks "why has unloading gone up this month", the
answer has to be visible. If coolie money were added into `unloading`, the
unloading sheet would silently disagree with the invoice and nobody could say
why. These tests pin that separation down.
"""

from decimal import Decimal

from app.models.enums import ChargeHead
from app.services.rating import RateTerms, TripFacts, calculate_freight_charge

# The verified Godrej card. Same numbers the invoice tests use, so a change in
# behaviour here shows up against a real document rather than a made-up one.
GODREJ = RateTerms(
    base_trip_amount=Decimal("1867"),
    included_km=60,
    extra_km_rate=Decimal("17"),
    included_points=3,
    extra_point_rate=Decimal("175"),
    base_point_charge=Decimal("0"),
)


def test_no_coolie_prices_exactly_as_before():
    """The default must be invisible.

    Every freight priced before coolie existed has to come out at the same
    rupee, or this change has silently rewritten history.
    """
    facts = TripFacts(km=900, points=7, toll=Decimal("290"))
    charge = calculate_freight_charge(GODREJ, facts)

    # 1867 + (900-60)*17 + (7-3)*175 + 290
    assert charge.line_total == Decimal("17137.00")
    assert charge.coolie == Decimal("0.00")


def test_coolie_adds_to_the_line_total():
    facts = TripFacts(km=900, points=7, toll=Decimal("290"), coolie=Decimal("450"))
    charge = calculate_freight_charge(GODREJ, facts)

    assert charge.coolie == Decimal("450.00")
    assert charge.line_total == Decimal("17587.00")


def test_coolie_is_not_added_into_unloading():
    """The distinction the whole head exists for."""
    facts = TripFacts(
        km=100,
        points=4,
        unloading=Decimal("900"),
        coolie=Decimal("450"),
    )
    charge = calculate_freight_charge(GODREJ, facts)

    assert charge.unloading == Decimal("900.00")
    assert charge.coolie == Decimal("450.00")

    heads = charge.by_head()
    assert heads[ChargeHead.LOADING_UNLOADING] == Decimal("900.00")
    assert heads[ChargeHead.COOLIE] == Decimal("450.00")


def test_coolie_has_its_own_head_distinct_from_every_other():
    facts = TripFacts(
        km=200,
        points=5,
        toll=Decimal("120"),
        unloading=Decimal("600"),
        unloading_additional=Decimal("90"),
        detention=Decimal("300"),
        coolie=Decimal("250"),
    )
    heads = calculate_freight_charge(GODREJ, facts).by_head()

    assert heads[ChargeHead.COOLIE] == Decimal("250.00")
    assert heads[ChargeHead.TOLL] == Decimal("120.00")
    assert heads[ChargeHead.DETENTION] == Decimal("300.00")
    # unloading + unloading_additional, and nothing else.
    assert heads[ChargeHead.LOADING_UNLOADING] == Decimal("690.00")


def test_heads_still_sum_to_the_line_total():
    """If a head is ever dropped from by_head, the invoice stops reconciling."""
    facts = TripFacts(
        km=900,
        points=7,
        toll=Decimal("290"),
        unloading=Decimal("600"),
        unloading_additional=Decimal("90"),
        detention=Decimal("150"),
        coolie=Decimal("450"),
    )
    charge = calculate_freight_charge(GODREJ, facts)

    assert sum(charge.by_head().values()) == charge.line_total


def test_coolie_appears_in_the_trace_only_when_charged():
    """The trace is what an operator reads to a vendor on the phone."""
    quiet = calculate_freight_charge(GODREJ, TripFacts(km=100, points=3))
    assert not any("oolie" in line for line in quiet.trace)

    loud = calculate_freight_charge(GODREJ, TripFacts(km=100, points=3, coolie=Decimal("450")))
    coolie_lines = [line for line in loud.trace if "oolie" in line]
    assert len(coolie_lines) == 1
    assert "450" in coolie_lines[0]


def test_coolie_survives_the_snapshot_round_trip():
    """as_dict feeds the stored line, which must reprint identically."""
    charge = calculate_freight_charge(
        GODREJ, TripFacts(km=900, points=7, toll=Decimal("290"), coolie=Decimal("450"))
    )
    data = charge.as_dict()

    assert data["coolie"] == "450.00"
    assert Decimal(data["line_total"]) == charge.line_total


def test_billed_is_independent_of_paid():
    """Two numbers on the point, for the same reason unloading has two.

    What the driver handed over at an unfamiliar market is not automatically
    what the vendor agreed to cover. Only the billed side reaches the invoice.
    """
    from app.models.freight import FreightPoint

    point = FreightPoint(
        sequence=1,
        coolie_paid=Decimal("600"),
        coolie_billed=Decimal("450"),
        coolie_note="Porter gang at Kasaragod market, demanded before unloading",
    )
    assert point.coolie_paid != point.coolie_billed
    assert point.coolie_note


def test_billable_coolie_sums_the_billed_side_across_points():
    from types import SimpleNamespace

    from app.services.invoicing import billable_coolie

    freight = SimpleNamespace(
        points=[
            SimpleNamespace(coolie_billed=Decimal("450")),
            SimpleNamespace(coolie_billed=Decimal("0")),
            SimpleNamespace(coolie_billed=Decimal("300")),
        ]
    )
    assert billable_coolie(freight) == Decimal("750.00")


def test_billable_coolie_tolerates_a_point_that_never_set_it():
    """Rows written before the column existed read back as None, not zero."""
    from types import SimpleNamespace

    from app.services.invoicing import billable_coolie

    freight = SimpleNamespace(
        points=[
            SimpleNamespace(coolie_billed=None),
            SimpleNamespace(coolie_billed=Decimal("450")),
        ]
    )
    assert billable_coolie(freight) == Decimal("450.00")
