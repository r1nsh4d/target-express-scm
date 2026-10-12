"""Unloading has two prices for the same chair.

The vendor is charged `a` for carrying a chair in. The driver is paid `b` for
carrying it. The difference is Target Express's margin on unloading, and it is
the whole reason the company handles unloading at all rather than leaving the
customer to arrange it.

Both numbers come off one rate row for one article on one date, so the margin
is a subtraction and never a reconciliation between two tables. These tests
hold that, and the one rule that overrides it: a driver is never left out of
pocket for cash he handed to labourers, whatever the rate card says.
"""

from decimal import Decimal

import pytest

from app.models.enums import ChargeHead, UnloadingShareBasis
from app.services.payout import DriverPayRates, LegFacts, compute_driver_payout
from app.services.unloading import (
    ItemRate,
    UnloadItem,
    calculate_point_driver_pay,
    calculate_point_unloading,
    division_pays_per_article,
)

# A chair earns Target Express 50 and costs 30 in driver pay. The climb is
# charged at 10 a floor and paid at 6.
CHAIR = ItemRate(
    item_code="CHAIR",
    item_name="Chair",
    base_rate=Decimal("50"),
    per_floor_rate=Decimal("10"),
    driver_base_rate=Decimal("30"),
    driver_per_floor_rate=Decimal("6"),
)
# A wardrobe is heavier work on both sides.
WARDROBE = ItemRate(
    item_code="WARDROBE",
    item_name="Wardrobe",
    base_rate=Decimal("200"),
    per_floor_rate=Decimal("40"),
    driver_base_rate=Decimal("120"),
    driver_per_floor_rate=Decimal("25"),
)
RATES = {"CHAIR": CHAIR, "WARDROBE": WARDROBE}


# ---------------------------------------------------------------------------
# The two sides of one article
# ---------------------------------------------------------------------------


def test_ground_floor_chair():
    items = [UnloadItem("CHAIR", 1)]
    assert calculate_point_unloading(RATES, items).total == Decimal("50.00")
    assert calculate_point_driver_pay(RATES, items).total == Decimal("30.00")


def test_the_margin_on_a_load():
    """Four chairs to the second floor.

    Vendor: (50 + 2x10) x 4 = 280. Driver: (30 + 2x6) x 4 = 168.
    Target Express keeps 112.
    """
    items = [UnloadItem("CHAIR", 4)]
    charged = calculate_point_unloading(RATES, items, floor_number=2).total
    paid = calculate_point_driver_pay(RATES, items, floor_number=2).total

    assert charged == Decimal("280.00")
    assert paid == Decimal("168.00")
    assert charged - paid == Decimal("112.00")


def test_a_mixed_load():
    items = [UnloadItem("CHAIR", 6), UnloadItem("WARDROBE", 2)]
    charged = calculate_point_unloading(RATES, items, floor_number=1).total
    paid = calculate_point_driver_pay(RATES, items, floor_number=1).total

    # Vendor: 6x60 + 2x240 = 840.  Driver: 6x36 + 2x145 = 506.
    assert charged == Decimal("840.00")
    assert paid == Decimal("506.00")
    assert charged - paid == Decimal("334.00")


def test_the_margin_never_goes_negative_on_these_rates():
    for floor in range(0, 6):
        for item in ("CHAIR", "WARDROBE"):
            items = [UnloadItem(item, 3)]
            charged = calculate_point_unloading(RATES, items, floor_number=floor).total
            paid = calculate_point_driver_pay(RATES, items, floor_number=floor).total
            assert charged >= paid, f"{item} at floor {floor} pays out more than it earns"


def test_the_climb_rules_are_the_same_on_both_sides():
    """If the vendor is not billed for a lift building the driver is not paid
    for one either. Two different rules for one staircase is how a margin turns
    negative on the one delivery nobody checked."""
    items = [UnloadItem("WARDROBE", 1)]
    charged = calculate_point_unloading(RATES, items, floor_number=4, has_lift=True).total
    paid = calculate_point_driver_pay(RATES, items, floor_number=4, has_lift=True).total

    assert charged == Decimal("200.00"), "lift cancelled the climb charge"
    assert paid == Decimal("120.00"), "lift must cancel the climb pay too"


# ---------------------------------------------------------------------------
# Which arrangement applies
# ---------------------------------------------------------------------------


def test_a_division_with_driver_rates_pays_per_article():
    assert division_pays_per_article(RATES) is True


def test_a_division_without_them_stays_on_the_percentage():
    """Spare parts: unloading is a flat cash amount, not an article list."""
    spares = {
        "SPARE": ItemRate(
            item_code="SPARE", item_name="Spare part", base_rate=Decimal("0")
        )
    }
    assert division_pays_per_article(spares) is False


def test_an_article_with_no_driver_rate_is_reported_not_paid_as_zero():
    """Paying nothing quietly for work a man did is the failure to avoid."""
    rates = dict(RATES)
    rates["MATTRESS"] = ItemRate(
        item_code="MATTRESS", item_name="Mattress", base_rate=Decimal("90")
    )
    pay = calculate_point_driver_pay(rates, [UnloadItem("MATTRESS", 2)])

    assert pay.total == Decimal("0.00")
    assert "MATTRESS" in pay.unpriced_item_codes


# ---------------------------------------------------------------------------
# What reaches the payout
# ---------------------------------------------------------------------------


def _rates() -> DriverPayRates:
    return DriverPayRates(
        per_km_amount=Decimal("0"),
        unloading_share_percent=Decimal("60"),
        unloading_share_basis=UnloadingShareBasis.PAID_AT_POINT,
    )


def _unloading_line(payout):
    return next(
        (ln for ln in payout.lines if ln.head == ChargeHead.LOADING_UNLOADING), None
    )


def test_the_article_pay_is_what_the_driver_gets():
    """Not the percentage. The rate card replaces it entirely."""
    payout = compute_driver_payout(
        _rates(),
        LegFacts(
            km=100,
            points=1,
            unloading_billed=Decimal("280"),
            unloading_paid=Decimal("0"),
            unloading_piece_pay=Decimal("168"),
        ),
    )
    line = _unloading_line(payout)
    assert line is not None
    assert line.amount == Decimal("168.00")
    assert "article rates" in line.basis


def test_the_line_says_what_target_express_keeps():
    """A driver asking where the rest went should be able to read the answer."""
    payout = compute_driver_payout(
        _rates(),
        LegFacts(
            km=100,
            points=1,
            unloading_billed=Decimal("280"),
            unloading_piece_pay=Decimal("168"),
        ),
    )
    assert "keeps 112.00" in _unloading_line(payout).basis


def test_a_driver_is_never_left_out_of_pocket():
    """He handed 400 to labourers and the article rates only earn him 168. The
    cash was his until it came back, so the payout is lifted to 400."""
    payout = compute_driver_payout(
        _rates(),
        LegFacts(
            km=100,
            points=1,
            unloading_billed=Decimal("280"),
            unloading_paid=Decimal("400"),
            unloading_piece_pay=Decimal("168"),
        ),
    )
    line = _unloading_line(payout)
    assert line.amount == Decimal("400.00")
    assert "never left out of pocket" in line.basis


def test_without_article_pay_the_percentage_still_applies():
    """The older arrangement is untouched for divisions that use it."""
    payout = compute_driver_payout(
        _rates(),
        LegFacts(
            km=100,
            points=1,
            unloading_paid=Decimal("500"),
            unloading_piece_pay=None,
        ),
    )
    assert _unloading_line(payout).amount == Decimal("300.00"), "60% of 500"


def test_zero_article_pay_is_not_the_same_as_no_arrangement():
    """A quiet day where nothing priced was carried must not silently move a
    driver onto the percentage scheme."""
    payout = compute_driver_payout(
        _rates(),
        LegFacts(
            km=100,
            points=1,
            unloading_paid=Decimal("500"),
            unloading_piece_pay=Decimal("0"),
        ),
    )
    # Out of pocket still comes back, but not 60% of it as earnings.
    line = _unloading_line(payout)
    assert line.amount == Decimal("500.00")
    assert "never left out of pocket" in line.basis


@pytest.mark.parametrize("floor,charged,paid", [(0, "50.00", "30.00"), (1, "60.00", "36.00"), (3, "80.00", "48.00")])
def test_one_chair_at_each_floor(floor, charged, paid):
    items = [UnloadItem("CHAIR", 1)]
    assert calculate_point_unloading(RATES, items, floor_number=floor).total == Decimal(charged)
    assert calculate_point_driver_pay(RATES, items, floor_number=floor).total == Decimal(paid)
