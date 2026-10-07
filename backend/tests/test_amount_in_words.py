"""The total in words, as a tax invoice carries it.

A GST invoice states the total in figures and again in words, and the vendor's
accounts team reads the second to check the first. If they disagree the invoice
is queried, so this is worth pinning down — particularly the Indian grouping,
which is lakh and crore rather than million.
"""

from decimal import Decimal

import pytest

from app.api.routes.company import amount_in_words


@pytest.mark.parametrize(
    "amount,expected",
    [
        (Decimal("0"), "Rupees Zero Only"),
        (Decimal("1"), "Rupees One Only"),
        (Decimal("17"), "Rupees Seventeen Only"),
        (Decimal("90"), "Rupees Ninety Only"),
        (Decimal("99"), "Rupees Ninety Nine Only"),
        (Decimal("100"), "Rupees One Hundred Only"),
        (Decimal("290"), "Rupees Two Hundred Ninety Only"),
        (Decimal("1867"), "Rupees One Thousand Eight Hundred Sixty Seven Only"),
    ],
)
def test_small_amounts(amount, expected):
    assert amount_in_words(amount) == expected


def test_the_verified_invoice_line():
    """17,137.00 — the Godrej freight the whole rate card was checked against."""
    assert amount_in_words(Decimal("17137.00")) == (
        "Rupees Seventeen Thousand One Hundred Thirty Seven Only"
    )


def test_a_whole_invoice_total():
    assert amount_in_words(Decimal("92478.40")) == (
        "Rupees Ninety Two Thousand Four Hundred Seventy Eight and Forty Paise Only"
    )


# ---------------------------------------------------------------------------
# Indian grouping
# ---------------------------------------------------------------------------


def test_lakhs_not_hundreds_of_thousands():
    """The whole reason this is not a library function.

    1,20,000 is One Lakh Twenty Thousand. A Western grouping would read it as
    One Hundred Twenty Thousand, which no Indian accounts team would accept on
    a tax invoice.
    """
    assert amount_in_words(Decimal("120000")) == "Rupees One Lakh Twenty Thousand Only"


def test_crores():
    assert amount_in_words(Decimal("12500000")) == "Rupees One Crore Twenty Five Lakh Only"


def test_crore_lakh_thousand_and_hundreds_together():
    assert amount_in_words(Decimal("23456789")) == (
        "Rupees Two Crore Thirty Four Lakh Fifty Six Thousand Seven Hundred Eighty Nine Only"
    )


# ---------------------------------------------------------------------------
# Paise
# ---------------------------------------------------------------------------


def test_paise_are_stated_separately():
    assert amount_in_words(Decimal("1234.56")) == (
        "Rupees One Thousand Two Hundred Thirty Four and Fifty Six Paise Only"
    )


def test_no_paise_clause_when_the_amount_is_whole():
    """"and Zero Paise" on every invoice would be noise."""
    assert "Paise" not in amount_in_words(Decimal("5000.00"))


def test_paise_round_rather_than_truncate():
    """A third decimal must not silently disappear: 0.455 is 46 paise, not 45."""
    assert "Forty Six Paise" in amount_in_words(Decimal("10.455"))


def test_paise_rounding_up_to_a_rupee_carries():
    """99.999 is a hundred rupees, not "Ninety Nine and One Hundred Paise".

    Left uncarried this was an IndexError, and had it not crashed it would have
    printed a line a rupee short of the figure above it on the same invoice.
    """
    assert amount_in_words(Decimal("99.999")) == "Rupees One Hundred Only"
    assert amount_in_words(Decimal("1866.996")) == "Rupees One Thousand Eight Hundred Sixty Seven Only"


def test_the_words_never_come_back_empty():
    """An invoice with a blank amount-in-words line is a queried invoice."""
    for value in ("0", "0.01", "7", "999999999"):
        words = amount_in_words(Decimal(value))
        assert words.startswith("Rupees")
        assert words.endswith("Only")
        assert len(words) > len("Rupees  Only")
