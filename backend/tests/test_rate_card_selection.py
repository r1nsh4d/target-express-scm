"""Which rate card prices a trip.

Rates are set per vendor division and per date. A mid-contract change is made by
adding a card dated from the change - trips before it keep pricing on the old
card, which is what lets an invoice from six months ago re-print unchanged.

This is the rule that decides what a vendor is charged, so it is tested on plain
objects rather than only through the database.
"""

from datetime import date

import pytest

from app.services.rating import covers, select_effective_card


class Card:
    """Stands in for a RateCard row. Only the fields selection reads."""

    def __init__(
        self,
        label: str,
        effective_from: date,
        effective_to: date | None = None,
        vehicle_type_id=None,
        is_active: bool = True,
    ):
        self.label = label
        self.effective_from = effective_from
        self.effective_to = effective_to
        self.vehicle_type_id = vehicle_type_id
        self.is_active = is_active

    def __repr__(self) -> str:
        return f"<Card {self.label}>"


APR = date(2026, 4, 1)
JUL = date(2026, 7, 1)
OCT = date(2026, 10, 1)


class TestDateWindows:
    def test_a_card_covers_its_own_start_date(self):
        assert covers(Card("a", APR), APR) is True

    def test_a_card_does_not_cover_the_day_before_it_starts(self):
        assert covers(Card("a", JUL), date(2026, 6, 30)) is False

    def test_an_open_ended_card_covers_any_later_date(self):
        assert covers(Card("a", APR), date(2030, 1, 1)) is True

    def test_the_closing_date_is_inclusive(self):
        """A card running to the 30th still prices a trip on the 30th."""
        card = Card("a", APR, effective_to=date(2026, 6, 30))
        assert covers(card, date(2026, 6, 30)) is True
        assert covers(card, date(2026, 7, 1)) is False

    def test_an_inactive_card_covers_nothing(self):
        assert covers(Card("a", APR, is_active=False), JUL) is False


class TestRateChangesMidContract:
    """The case behind the whole design: the included-points figure or the
    per-point rate moves, and old trips must keep their old price."""

    OLD = Card("3 points included", APR, effective_to=date(2026, 6, 30))
    NEW = Card("5 points included", JUL)
    CARDS = [OLD, NEW]

    @pytest.mark.parametrize(
        "trip_date,expected",
        [
            (date(2026, 4, 1), "3 points included"),
            (date(2026, 6, 30), "3 points included"),
            (date(2026, 7, 1), "5 points included"),
            (date(2026, 12, 25), "5 points included"),
        ],
    )
    def test_the_card_in_force_on_the_trip_date_is_used(self, trip_date, expected):
        assert select_effective_card(self.CARDS, trip_date).label == expected

    def test_order_of_the_cards_does_not_matter(self):
        assert select_effective_card(list(reversed(self.CARDS)), APR).label == (
            "3 points included"
        )

    def test_a_trip_before_any_card_has_no_rate(self):
        assert select_effective_card(self.CARDS, date(2026, 1, 1)) is None

    def test_a_gap_between_cards_has_no_rate(self):
        """Better to refuse than to quietly price on a lapsed card."""
        cards = [
            Card("first", APR, effective_to=date(2026, 6, 30)),
            Card("second", OCT),
        ]
        assert select_effective_card(cards, date(2026, 8, 15)) is None


class TestOverlappingCards:
    def test_the_latest_start_date_wins(self):
        cards = [
            Card("older", APR),
            Card("newer", JUL),
        ]
        assert select_effective_card(cards, OCT).label == "newer"

    def test_an_older_card_still_applies_before_the_newer_one_starts(self):
        cards = [Card("older", APR), Card("newer", JUL)]
        assert select_effective_card(cards, date(2026, 5, 1)).label == "older"


class TestVehicleTypePrecedence:
    DOST = "vt-dost"
    TRUCK = "vt-truck"

    CARDS = [
        Card("catch-all", APR),
        Card("dost only", APR, vehicle_type_id=DOST),
    ]

    def test_a_card_naming_the_vehicle_type_beats_the_catch_all(self):
        assert select_effective_card(self.CARDS, JUL, vehicle_type_id=self.DOST).label == (
            "dost only"
        )

    def test_an_unnamed_vehicle_type_falls_back_to_the_catch_all(self):
        assert select_effective_card(self.CARDS, JUL, vehicle_type_id=self.TRUCK).label == (
            "catch-all"
        )

    def test_no_vehicle_type_given_uses_the_catch_all(self):
        assert select_effective_card(self.CARDS, JUL).label == "catch-all"

    def test_godrej_has_only_catch_all_cards(self):
        """Their invoices show the same rate across vehicle types, so the
        specific-card path is unused there - but it costs nothing to keep."""
        cards = [Card("godrej", APR)]
        assert select_effective_card(cards, JUL, vehicle_type_id=self.DOST).label == "godrej"

    def test_a_lapsed_specific_card_falls_back_rather_than_failing(self):
        cards = [
            Card("catch-all", APR),
            Card("dost only", APR, effective_to=date(2026, 6, 30), vehicle_type_id=self.DOST),
        ]
        assert select_effective_card(cards, JUL, vehicle_type_id=self.DOST).label == (
            "catch-all"
        )


class TestNoCards:
    def test_an_empty_list_has_no_rate(self):
        assert select_effective_card([], JUL) is None

    def test_only_inactive_cards_means_no_rate(self):
        assert select_effective_card([Card("a", APR, is_active=False)], JUL) is None
