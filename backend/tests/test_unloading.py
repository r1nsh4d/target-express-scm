"""Furniture unloading, priced per article plus the climb.

The worked example from the client: a chair at 50 with 10 a floor, delivered to
the 4th floor, unloads at 90.
"""

from decimal import Decimal

from app.services.rating import money
from app.services.unloading import (
    ItemRate,
    UnloadItem,
    calculate_point_unloading,
    items_from_boxes,
)

CHAIR = ItemRate(
    item_code="CHAIR",
    item_name="Chair",
    base_rate=Decimal("50"),
    per_floor_rate=Decimal("10"),
)
WARDROBE = ItemRate(
    item_code="WARDROBE",
    item_name="Wardrobe",
    base_rate=Decimal("400"),
    per_floor_rate=Decimal("80"),
)
RATES = {r.item_code: r for r in (CHAIR, WARDROBE)}


class TestTheWorkedExample:
    def test_chair_to_the_fourth_floor_is_ninety(self):
        result = calculate_point_unloading(
            RATES, [UnloadItem("CHAIR")], floor_number=4
        )
        assert result.total == money("90.00")

    def test_chair_on_the_ground_floor_is_the_base_rate(self):
        result = calculate_point_unloading(
            RATES, [UnloadItem("CHAIR")], floor_number=0
        )
        assert result.total == money("50.00")

    def test_the_line_explains_the_climb(self):
        result = calculate_point_unloading(
            RATES, [UnloadItem("CHAIR")], floor_number=4
        )
        assert result.lines[0].basis == "1 x Chair: 50 + 4 floor(s) x 10 = 90.00 each"

    def test_quantity_multiplies(self):
        result = calculate_point_unloading(
            RATES, [UnloadItem("CHAIR", quantity=6)], floor_number=4
        )
        assert result.total == money("540.00")
        assert result.item_count == 6


class TestArticlesArePricedSeparately:
    def test_different_articles_carry_different_rates(self):
        result = calculate_point_unloading(
            RATES,
            [UnloadItem("CHAIR", quantity=4), UnloadItem("WARDROBE", quantity=1)],
            floor_number=2,
        )
        # Chairs: (50 + 2x10) x 4 = 280. Wardrobe: 400 + 2x80 = 560.
        assert result.total == money("840.00")

    def test_a_single_point_can_mix_articles(self):
        result = calculate_point_unloading(
            RATES,
            [UnloadItem("CHAIR", quantity=2), UnloadItem("WARDROBE", quantity=3)],
            floor_number=0,
        )
        assert result.total == money("1300.00")  # 100 + 1200
        assert len(result.lines) == 2


class TestFloors:
    def test_every_floor_above_ground_is_charged(self):
        for floor, expected in [(0, "50"), (1, "60"), (2, "70"), (5, "100"), (10, "150")]:
            result = calculate_point_unloading(
                RATES, [UnloadItem("CHAIR")], floor_number=floor
            )
            assert result.total == money(expected), f"floor {floor}"

    def test_a_lift_cancels_the_climb_charge_by_default(self):
        result = calculate_point_unloading(
            RATES, [UnloadItem("CHAIR")], floor_number=4, has_lift=True
        )
        assert result.total == money("50.00")
        assert "lift available" in result.lines[0].basis

    def test_a_division_can_charge_floors_even_with_a_lift(self):
        rates = {
            "CHAIR": ItemRate(
                item_code="CHAIR",
                item_name="Chair",
                base_rate=Decimal("50"),
                per_floor_rate=Decimal("10"),
                charge_floors_with_lift=True,
            )
        }
        result = calculate_point_unloading(
            rates, [UnloadItem("CHAIR")], floor_number=4, has_lift=True
        )
        assert result.total == money("90.00")

    def test_a_cap_stops_the_climb_charge_growing(self):
        rates = {
            "CHAIR": ItemRate(
                item_code="CHAIR",
                item_name="Chair",
                base_rate=Decimal("50"),
                per_floor_rate=Decimal("10"),
                max_chargeable_floors=3,
            )
        }
        result = calculate_point_unloading(
            rates, [UnloadItem("CHAIR")], floor_number=9
        )
        assert result.total == money("80.00")  # 50 + 3 x 10, not 9


class TestUnpricedArticles:
    def test_an_article_with_no_rate_is_surfaced_not_silently_billed(self):
        result = calculate_point_unloading(
            RATES,
            [UnloadItem("CHAIR"), UnloadItem("RECLINER", quantity=2)],
            floor_number=1,
        )
        assert result.total == money("60.00")
        assert result.unpriced_item_codes == ["RECLINER"]

    def test_a_fully_priced_point_reports_nothing_unpriced(self):
        result = calculate_point_unloading(RATES, [UnloadItem("CHAIR")], floor_number=1)
        assert result.unpriced_item_codes == []


class TestRollingBoxesUpIntoArticles:
    class FakeBox:
        def __init__(self, item_code):
            self.item_code = item_code

    def test_boxes_group_by_article_code(self):
        boxes = [self.FakeBox(c) for c in ["CHAIR", "CHAIR", "WARDROBE", "CHAIR"]]
        items = items_from_boxes(boxes)
        assert items == [UnloadItem("CHAIR", 3), UnloadItem("WARDROBE", 1)]

    def test_boxes_without_an_article_code_are_ignored(self):
        boxes = [self.FakeBox("CHAIR"), self.FakeBox(None), self.FakeBox("")]
        assert items_from_boxes(boxes) == [UnloadItem("CHAIR", 1)]

    def test_grouped_boxes_price_correctly(self):
        boxes = [self.FakeBox("CHAIR") for _ in range(4)]
        result = calculate_point_unloading(RATES, items_from_boxes(boxes), floor_number=4)
        assert result.total == money("360.00")  # 4 chairs x 90
