"""Freight-level rules: which points bill, and when a trip is finished.

These properties are plain Python on the model, so they can be exercised on
in-memory objects without a database.
"""

from app.models.enums import FreightPointStatus
from app.models.freight import Freight, FreightLeg, FreightPoint


def freight_with(statuses: list[FreightPointStatus]) -> Freight:
    freight = Freight()
    freight.points = [
        FreightPoint(sequence=i + 1, status=status) for i, status in enumerate(statuses)
    ]
    return freight


class TestBillablePoints:
    """A failed delivery still bills: the vehicle went there, and that journey
    is the work being charged for."""

    def test_a_failed_delivery_still_counts(self):
        freight = freight_with(
            [
                FreightPointStatus.DELIVERED,
                FreightPointStatus.DELIVERED,
                FreightPointStatus.FAILED,
            ]
        )
        assert freight.billable_point_count == 3
        assert freight.delivered_point_count == 2

    def test_a_part_delivery_counts_on_both_sides(self):
        freight = freight_with(
            [FreightPointStatus.DELIVERED, FreightPointStatus.PART_DELIVERED]
        )
        assert freight.billable_point_count == 2
        assert freight.delivered_point_count == 2

    def test_a_skipped_point_does_not_bill(self):
        """Pulled from the route before setting off, so no journey was made."""
        freight = freight_with(
            [
                FreightPointStatus.DELIVERED,
                FreightPointStatus.SKIPPED,
                FreightPointStatus.FAILED,
            ]
        )
        assert freight.billable_point_count == 2

    def test_a_trip_where_everything_failed_still_bills_every_point(self):
        freight = freight_with([FreightPointStatus.FAILED] * 4)
        assert freight.billable_point_count == 4
        assert freight.delivered_point_count == 0

    def test_an_empty_trip_bills_nothing(self):
        assert freight_with([]).billable_point_count == 0


class TestCompletionNeedsTheReturn:
    """A trip is finished when the vehicle is back at the warehouse it left
    from, not when the last point is delivered."""

    def test_an_open_leg_means_the_trip_is_still_running(self):
        freight = freight_with([FreightPointStatus.DELIVERED] * 3)
        freight.legs = [FreightLeg(sequence=1, start_odometer=1000, end_odometer=None)]
        assert freight.has_returned is False

    def test_every_point_delivered_is_not_enough(self):
        freight = freight_with([FreightPointStatus.DELIVERED] * 5)
        freight.legs = [FreightLeg(sequence=1, start_odometer=1000)]
        assert freight.has_returned is False

    def test_a_closed_leg_means_the_vehicle_is_back(self):
        freight = freight_with([FreightPointStatus.DELIVERED] * 3)
        freight.legs = [
            FreightLeg(sequence=1, start_odometer=1000, end_odometer=1345, leg_distance_km=345)
        ]
        assert freight.has_returned is True
        assert freight.round_trip_km == 345

    def test_a_swapped_vehicle_needs_both_legs_closed(self):
        freight = freight_with([FreightPointStatus.DELIVERED] * 6)
        freight.legs = [
            FreightLeg(sequence=1, start_odometer=1000, end_odometer=1180, leg_distance_km=180),
            FreightLeg(sequence=2, start_odometer=5000, end_odometer=None),
        ]
        assert freight.has_returned is False

        freight.legs[1].end_odometer = 5220
        freight.legs[1].leg_distance_km = 220
        assert freight.has_returned is True
        # Billed distance is the whole loop, across both vehicles.
        assert freight.round_trip_km == 400

    def test_a_trip_with_no_legs_has_not_returned(self):
        freight = freight_with([FreightPointStatus.DELIVERED])
        freight.legs = []
        assert freight.has_returned is False
