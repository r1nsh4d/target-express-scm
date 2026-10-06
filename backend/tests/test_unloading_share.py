"""How the unloading charge splits between the driver and Target Express.

The arrangement: the vendor pays for unloading, the driver takes an agreed
share, Target Express keeps the rest. The hard part is "a share of WHAT",
because there are two pots and they are rarely the same number:

    PAID_AT_POINT     a share of the cash that went out at the stops
    BILLED_TO_VENDOR  a share of what the vendor was charged

The trap these tests exist to hold shut: on a SPARE PARTS run the vendor is
billed nothing at all for unloading, while the driver still hands cash to the
labourers. A straight percentage of the billed amount is zero, which would
leave that driver funding Target Express's unloading out of his own pocket.
"""

from decimal import Decimal

from app.models.enums import ChargeHead, UnloadingShareBasis, VehicleOwnership
from app.services.payout import (
    DriverPayRates,
    LegFacts,
    compute_leg_payout,
)
from app.services.rating import money


def _payout(rates: DriverPayRates, facts: LegFacts):
    return compute_leg_payout(VehicleOwnership.OWNED, facts, driver_rates=rates)


def _unloading(rates: DriverPayRates, facts: LegFacts) -> Decimal:
    return _payout(rates, facts).by_head(ChargeHead.LOADING_UNLOADING)


# ---------------------------------------------------------------------------
# The default basis
# ---------------------------------------------------------------------------


def test_the_default_basis_is_what_was_paid_out():
    """Changing this default silently changes what every driver is paid."""
    assert DriverPayRates().unloading_share_basis == UnloadingShareBasis.PAID_AT_POINT


def test_paid_basis_takes_the_agreed_share_and_no_more():
    """A share below 100% is the arrangement, not a mistake to be corrected."""
    rates = DriverPayRates(unloading_share_percent=Decimal("60"))
    assert _unloading(rates, LegFacts(unloading_paid=Decimal("500"))) == money("300.00")


def test_paid_basis_at_full_share_is_a_straight_reimbursement():
    rates = DriverPayRates(unloading_share_percent=Decimal("100"))
    assert _unloading(rates, LegFacts(unloading_paid=Decimal("700"))) == money("700.00")


# ---------------------------------------------------------------------------
# The billed basis — a true split of one pot
# ---------------------------------------------------------------------------


def test_billed_basis_splits_what_the_vendor_was_charged():
    """Vendor pays 900, driver's 70% is 630, Target Express keeps 270."""
    rates = DriverPayRates(
        unloading_share_percent=Decimal("70"),
        unloading_share_basis=UnloadingShareBasis.BILLED_TO_VENDOR,
    )
    facts = LegFacts(unloading_billed=Decimal("900"), unloading_paid=Decimal("600"))

    assert _unloading(rates, facts) == money("630.00")


def test_billed_basis_names_what_target_express_keeps():
    """The settlement document is read by the driver. The retained share is
    stated rather than left as a number he has to work out."""
    rates = DriverPayRates(
        unloading_share_percent=Decimal("70"),
        unloading_share_basis=UnloadingShareBasis.BILLED_TO_VENDOR,
    )
    facts = LegFacts(unloading_billed=Decimal("900"), unloading_paid=Decimal("600"))

    line = next(
        l for l in _payout(rates, facts).lines if l.head == ChargeHead.LOADING_UNLOADING
    )
    assert "900" in line.basis
    assert "billed to the vendor" in line.basis
    assert "270" in line.basis


def test_the_two_bases_pay_different_money_on_the_same_trip():
    """Which is exactly why the basis is stored rather than assumed."""
    facts = LegFacts(unloading_billed=Decimal("900"), unloading_paid=Decimal("600"))
    percent = Decimal("70")

    on_paid = _unloading(
        DriverPayRates(
            unloading_share_percent=percent,
            unloading_share_basis=UnloadingShareBasis.PAID_AT_POINT,
        ),
        facts,
    )
    on_billed = _unloading(
        DriverPayRates(
            unloading_share_percent=percent,
            unloading_share_basis=UnloadingShareBasis.BILLED_TO_VENDOR,
        ),
        facts,
    )

    assert on_paid == money("420.00")    # 70% of the 600 that went out
    assert on_billed == money("630.00")  # 70% of the 900 the vendor was charged
    assert on_paid != on_billed


# ---------------------------------------------------------------------------
# The spare-parts trap
# ---------------------------------------------------------------------------


def test_spare_parts_driver_is_not_left_out_of_pocket():
    """The case the whole floor exists for.

    Spare parts bill the vendor NOTHING for unloading. The driver still paid
    700 to the labourers. A straight 70% of 0 is 0, and he would be 700 down on
    a run he did for the company.
    """
    rates = DriverPayRates(
        unloading_share_percent=Decimal("70"),
        unloading_share_basis=UnloadingShareBasis.BILLED_TO_VENDOR,
    )
    facts = LegFacts(unloading_billed=Decimal("0"), unloading_paid=Decimal("700"))

    assert _unloading(rates, facts) == money("700.00")


def test_the_floor_says_so_on_the_settlement():
    """A driver reading his settlement must see why the number is what it is,
    not just that it is more than the percentage implies."""
    rates = DriverPayRates(
        unloading_share_percent=Decimal("70"),
        unloading_share_basis=UnloadingShareBasis.BILLED_TO_VENDOR,
    )
    facts = LegFacts(unloading_billed=Decimal("0"), unloading_paid=Decimal("700"))

    line = next(
        l for l in _payout(rates, facts).lines if l.head == ChargeHead.LOADING_UNLOADING
    )
    assert "out of pocket" in line.basis
    assert "700" in line.basis


def test_the_floor_does_not_apply_on_the_paid_basis():
    """Otherwise any share below 100% would be silently ignored, and
    unloading_share_percent would do nothing at all."""
    rates = DriverPayRates(
        unloading_share_percent=Decimal("60"),
        unloading_share_basis=UnloadingShareBasis.PAID_AT_POINT,
    )
    assert _unloading(rates, LegFacts(unloading_paid=Decimal("500"))) == money("300.00")


def test_billed_basis_does_not_floor_when_the_share_already_exceeds_the_cash():
    """A healthy furniture job: the split stands, nothing is lifted."""
    rates = DriverPayRates(
        unloading_share_percent=Decimal("70"),
        unloading_share_basis=UnloadingShareBasis.BILLED_TO_VENDOR,
    )
    facts = LegFacts(unloading_billed=Decimal("900"), unloading_paid=Decimal("400"))

    line = next(
        l for l in _payout(rates, facts).lines if l.head == ChargeHead.LOADING_UNLOADING
    )
    assert line.amount == money("630.00")
    assert "out of pocket" not in line.basis
    assert "Target Express keeps 270" in line.basis


# ---------------------------------------------------------------------------
# Coolie money is reimbursed, never shared
# ---------------------------------------------------------------------------


def test_coolie_is_reimbursed_in_full_whatever_the_unloading_share():
    """It is not earnings.

    A porter gang demanded cash before they would let the lorry be unloaded and
    the driver paid it. Applying his unloading share to that would mean the
    driver personally funding part of somebody else's extortion.
    """
    rates = DriverPayRates(
        unloading_share_percent=Decimal("60"),
        unloading_share_basis=UnloadingShareBasis.PAID_AT_POINT,
    )
    facts = LegFacts(unloading_paid=Decimal("500"), coolie_paid=Decimal("450"))

    payout = _payout(rates, facts)
    assert payout.by_head(ChargeHead.COOLIE) == money("450.00")
    # ...and it did not touch the unloading share.
    assert payout.by_head(ChargeHead.LOADING_UNLOADING) == money("300.00")


def test_coolie_is_its_own_head_not_more_unloading():
    rates = DriverPayRates(unloading_share_percent=Decimal("100"))
    facts = LegFacts(unloading_paid=Decimal("700"), coolie_paid=Decimal("450"))

    payout = _payout(rates, facts)
    heads = [line.head for line in payout.lines]
    assert ChargeHead.COOLIE in heads
    assert heads.count(ChargeHead.LOADING_UNLOADING) == 1
    assert payout.by_head(ChargeHead.LOADING_UNLOADING) == money("700.00")


def test_no_coolie_line_when_none_was_paid():
    """The common case. A settlement should not list a zero."""
    payout = _payout(
        DriverPayRates(unloading_share_percent=Decimal("100")),
        LegFacts(unloading_paid=Decimal("700")),
    )
    assert all(line.head != ChargeHead.COOLIE for line in payout.lines)


def test_coolie_explains_itself_on_the_settlement():
    payout = _payout(DriverPayRates(), LegFacts(coolie_paid=Decimal("450")))
    line = next(l for l in payout.lines if l.head == ChargeHead.COOLIE)
    assert "reimbursed" in line.basis
    assert "not earnings" in line.basis


def test_coolie_reaches_the_total():
    rates = DriverPayRates(per_km_amount=Decimal("2.50"), unloading_share_percent=Decimal("100"))
    facts = LegFacts(km=100, unloading_paid=Decimal("700"), coolie_paid=Decimal("450"))

    # 100 km x 2.50 = 250, + 700 unloading, + 450 coolie
    assert _payout(rates, facts).total == money("1400.00")
