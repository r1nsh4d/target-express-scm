"""Payout tests: who gets paid, under which head, and how much.

The rule being protected is that the payee follows the VEHICLE, not the trip.
An owned vehicle pays its driver; a rented one pays the vehicle's owner, who
settles with his own driver.
"""

from decimal import Decimal

import pytest

from app.models.enums import ChargeHead, HireRateBasis, PayeeType, VehicleOwnership
from app.services.payout import (
    DriverPayRates,
    HireRates,
    LegFacts,
    TripMargin,
    compute_leg_payout,
    resolve_payee,
)
from app.services.rating import RateTerms, TripFacts, calculate_freight_charge, money

DRIVER = DriverPayRates(
    per_trip_amount=Decimal("450"),
    per_km_amount=Decimal("1.50"),
    per_point_amount=Decimal("40"),
    daily_allowance=Decimal("250"),
    unloading_share_percent=Decimal("100"),
)

HIRE_PER_KM = HireRates(
    rate_basis=HireRateBasis.PER_KM,
    rate_value=Decimal("13.00"),
    minimum_km_per_trip=150,
)

GODREJ = RateTerms(
    base_trip_amount=Decimal("1867.00"),
    included_km=60,
    extra_km_rate=Decimal("17.00"),
    included_points=3,
    extra_point_rate=Decimal("175.00"),
)


class TestPayeeFollowsTheVehicle:
    def test_owned_vehicle_pays_the_driver(self):
        assert resolve_payee(VehicleOwnership.OWNED) == PayeeType.DRIVER

    def test_rented_vehicle_pays_the_owner(self):
        assert resolve_payee(VehicleOwnership.HIRED) == PayeeType.VEHICLE_OWNER

    def test_rented_vehicle_without_hire_terms_is_an_error(self):
        with pytest.raises(ValueError, match="hire terms"):
            compute_leg_payout(VehicleOwnership.HIRED, LegFacts(km=300), driver_rates=DRIVER)

    def test_owned_vehicle_without_pay_terms_is_an_error(self):
        with pytest.raises(ValueError, match="driver pay terms"):
            compute_leg_payout(VehicleOwnership.OWNED, LegFacts(km=300), hire_rates=HIRE_PER_KM)


class TestTheStandardDriverArrangement:
    """How Target Express actually pays its drivers: distance, plus the
    unloading cash. Nothing for points."""

    STANDARD = DriverPayRates(
        per_km_amount=Decimal("2.50"),
        unloading_share_percent=Decimal("100"),
    )

    def test_transportation_is_distance_alone(self):
        payout = compute_leg_payout(
            VehicleOwnership.OWNED, LegFacts(km=345, points=7), driver_rates=self.STANDARD
        )
        assert payout.by_head(ChargeHead.TRANSPORTATION) == money("862.50")

    def test_points_earn_the_driver_nothing(self):
        payout = compute_leg_payout(
            VehicleOwnership.OWNED, LegFacts(km=345, points=12), driver_rates=self.STANDARD
        )
        assert payout.by_head(ChargeHead.POINT_INCENTIVE) == money("0")

    def test_unloading_passes_through_in_full(self):
        payout = compute_leg_payout(
            VehicleOwnership.OWNED,
            LegFacts(km=345, points=7, unloading_paid=Decimal("700")),
            driver_rates=self.STANDARD,
        )
        assert payout.by_head(ChargeHead.LOADING_UNLOADING) == money("700.00")

    def test_the_vendor_point_charge_is_retained_margin(self):
        """The vendor pays for extra points; the driver does not see it."""
        billed = calculate_freight_charge(GODREJ, TripFacts(km=345, points=7)).by_head()
        paid = compute_leg_payout(
            VehicleOwnership.OWNED, LegFacts(km=345, points=7), driver_rates=self.STANDARD
        )

        assert billed[ChargeHead.POINT_INCENTIVE] == money("700.00")
        assert paid.by_head(ChargeHead.POINT_INCENTIVE) == money("0")

    def test_whole_trip(self):
        payout = compute_leg_payout(
            VehicleOwnership.OWNED,
            LegFacts(km=345, points=7, unloading_paid=Decimal("700")),
            driver_rates=self.STANDARD,
        )
        assert payout.total == money("1562.50")  # 862.50 km + 700 unloading


class TestDriverPayout:
    """A fuller arrangement, exercising every field. Not the norm, but the
    engine has to support a driver on a trip rate or a daily allowance."""

    FACTS = LegFacts(km=345, points=7, unloading_paid=Decimal("700"), days=1)

    def payout(self):
        return compute_leg_payout(VehicleOwnership.OWNED, self.FACTS, driver_rates=DRIVER)

    def test_transportation_head(self):
        # 450 trip + 345 km x 1.50 + 1 day x 250
        assert self.payout().by_head(ChargeHead.TRANSPORTATION) == money("1217.50")

    def test_point_incentive_head(self):
        assert self.payout().by_head(ChargeHead.POINT_INCENTIVE) == money("280.00")

    def test_the_driver_incentive_can_also_start_after_a_threshold(self):
        """Mirrors the vendor side: pay the incentive only past N stops."""
        rates = DriverPayRates(per_point_amount=Decimal("40"), incentive_after_points=3)
        payout = compute_leg_payout(
            VehicleOwnership.OWNED, LegFacts(points=7), driver_rates=rates
        )
        # 7 stops, first 3 do not earn: 4 x 40.
        assert payout.by_head(ChargeHead.POINT_INCENTIVE) == money("160.00")

    def test_no_threshold_means_every_point_earns(self):
        rates = DriverPayRates(per_point_amount=Decimal("40"))
        payout = compute_leg_payout(
            VehicleOwnership.OWNED, LegFacts(points=7), driver_rates=rates
        )
        assert payout.by_head(ChargeHead.POINT_INCENTIVE) == money("280.00")

    def test_a_trip_below_the_threshold_earns_no_incentive(self):
        rates = DriverPayRates(per_point_amount=Decimal("40"), incentive_after_points=5)
        payout = compute_leg_payout(
            VehicleOwnership.OWNED, LegFacts(points=3), driver_rates=rates
        )
        assert payout.by_head(ChargeHead.POINT_INCENTIVE) == money("0")

    def test_unloading_head_is_his_share_of_what_he_paid_out(self):
        assert self.payout().by_head(ChargeHead.LOADING_UNLOADING) == money("700.00")

    def test_partial_unloading_share(self):
        rates = DriverPayRates(unloading_share_percent=Decimal("60"))
        payout = compute_leg_payout(
            VehicleOwnership.OWNED,
            LegFacts(unloading_paid=Decimal("500")),
            driver_rates=rates,
        )
        assert payout.by_head(ChargeHead.LOADING_UNLOADING) == money("300.00")

    def test_total(self):
        assert self.payout().total == money("2197.50")

    def test_every_line_explains_itself(self):
        for line in self.payout().lines:
            assert line.basis, f"{line.head} has no basis text"


class TestOwnerPayout:
    def test_per_km_hire(self):
        payout = compute_leg_payout(
            VehicleOwnership.HIRED,
            LegFacts(km=345, unloading_paid=Decimal("700")),
            hire_rates=HIRE_PER_KM,
        )
        assert payout.payee_type == PayeeType.VEHICLE_OWNER
        assert payout.by_head(ChargeHead.TRANSPORTATION) == money("4485.00")

    def test_minimum_km_guarantee_applies_to_a_short_trip(self):
        payout = compute_leg_payout(
            VehicleOwnership.HIRED, LegFacts(km=80), hire_rates=HIRE_PER_KM
        )
        # Ran 80 km, billed the 150 km floor.
        assert payout.by_head(ChargeHead.TRANSPORTATION) == money("1950.00")
        assert "minimum 150 km applied, ran 80" in payout.lines[0].basis

    def test_flat_trip_hire(self):
        rates = HireRates(rate_basis=HireRateBasis.PER_TRIP, rate_value=Decimal("4200"))
        payout = compute_leg_payout(
            VehicleOwnership.HIRED, LegFacts(km=612), hire_rates=rates
        )
        assert payout.by_head(ChargeHead.TRANSPORTATION) == money("4200.00")

    def test_per_day_hire(self):
        rates = HireRates(rate_basis=HireRateBasis.PER_DAY, rate_value=Decimal("2500"))
        payout = compute_leg_payout(
            VehicleOwnership.HIRED, LegFacts(km=300, days=3), hire_rates=rates
        )
        assert payout.by_head(ChargeHead.TRANSPORTATION) == money("7500.00")

    def test_unloading_goes_to_the_driver_not_the_owner(self):
        """The hire settles to the owner, but the unloading cash goes to the
        driver: he is the one who paid the labourers and splits it with the
        cleaner."""
        payout = compute_leg_payout(
            VehicleOwnership.HIRED,
            LegFacts(km=345, unloading_paid=Decimal("700")),
            hire_rates=HIRE_PER_KM,
        )
        assert payout.by_head(ChargeHead.LOADING_UNLOADING, PayeeType.DRIVER) == money("700.00")
        assert payout.by_head(
            ChargeHead.LOADING_UNLOADING, PayeeType.VEHICLE_OWNER
        ) == money("0")

    def test_a_rented_leg_can_pay_two_parties(self):
        payout = compute_leg_payout(
            VehicleOwnership.HIRED,
            LegFacts(km=345, unloading_paid=Decimal("700")),
            hire_rates=HIRE_PER_KM,
        )
        assert payout.payees == [PayeeType.VEHICLE_OWNER, PayeeType.DRIVER]
        assert payout.total_for(PayeeType.VEHICLE_OWNER) == money("4485.00")
        assert payout.total_for(PayeeType.DRIVER) == money("700.00")

    def test_unloading_can_be_routed_to_the_owner_where_agreed(self):
        rates = HireRates(
            rate_basis=HireRateBasis.PER_KM,
            rate_value=Decimal("13.00"),
            unloading_paid_to_owner=True,
        )
        payout = compute_leg_payout(
            VehicleOwnership.HIRED,
            LegFacts(km=345, unloading_paid=Decimal("700")),
            hire_rates=rates,
        )
        assert payout.total_for(PayeeType.DRIVER) == money("0")
        assert payout.by_head(
            ChargeHead.LOADING_UNLOADING, PayeeType.VEHICLE_OWNER
        ) == money("700.00")

    def test_unloading_is_not_paid_twice_when_the_rent_includes_it(self):
        rates = HireRates(
            rate_basis=HireRateBasis.PER_KM,
            rate_value=Decimal("13.00"),
            includes_unloading=True,
        )
        payout = compute_leg_payout(
            VehicleOwnership.HIRED,
            LegFacts(km=345, unloading_paid=Decimal("700")),
            hire_rates=rates,
        )
        assert payout.by_head(ChargeHead.LOADING_UNLOADING) == money("0")

    def test_point_incentive_is_off_by_default_on_a_rental(self):
        payout = compute_leg_payout(
            VehicleOwnership.HIRED, LegFacts(km=345, points=9), hire_rates=HIRE_PER_KM
        )
        assert payout.by_head(ChargeHead.POINT_INCENTIVE) == money("0")


class TestHeadsLineUpOnBothSides:
    """The billed side and the paid side must group under the same heads, or
    margin cannot be read head by head."""

    FACTS = LegFacts(km=345, points=7, unloading_paid=Decimal("700"))

    def test_billed_heads_match_payout_heads(self):
        billed = calculate_freight_charge(
            GODREJ, TripFacts(km=345, points=7, unloading=Decimal("700"))
        ).by_head()
        paid = compute_leg_payout(VehicleOwnership.OWNED, self.FACTS, driver_rates=DRIVER)

        for head in (
            ChargeHead.TRANSPORTATION,
            ChargeHead.LOADING_UNLOADING,
            ChargeHead.POINT_INCENTIVE,
        ):
            assert head in billed
            assert isinstance(paid.by_head(head), Decimal)

    def test_billed_transportation_is_base_plus_distance(self):
        billed = calculate_freight_charge(GODREJ, TripFacts(km=345, points=7)).by_head()
        # 1867 base + (345 - 60) x 17
        assert billed[ChargeHead.TRANSPORTATION] == money("6712.00")

    def test_billed_point_incentive_is_the_extra_points(self):
        billed = calculate_freight_charge(GODREJ, TripFacts(km=345, points=7)).by_head()
        assert billed[ChargeHead.POINT_INCENTIVE] == money("700.00")

    def test_margin_on_an_owned_vehicle(self):
        charge = calculate_freight_charge(
            GODREJ, TripFacts(km=345, points=7, unloading=Decimal("700"))
        )
        paid = compute_leg_payout(VehicleOwnership.OWNED, self.FACTS, driver_rates=DRIVER)

        m = TripMargin(billed=charge.line_total, paid=paid.total)
        assert m.billed == money("8112.00")
        assert m.paid == money("2197.50")
        assert m.margin == money("5914.50")

    def test_unloading_margin_is_zero_when_billed_equals_paid(self):
        """Spare parts bill nothing for unloading while cash still goes out -
        the case that makes a single shared field wrong."""
        charge = calculate_freight_charge(GODREJ, TripFacts(km=345, points=7))
        paid = compute_leg_payout(VehicleOwnership.OWNED, self.FACTS, driver_rates=DRIVER)

        billed_unloading = charge.by_head()[ChargeHead.LOADING_UNLOADING]
        paid_unloading = paid.by_head(ChargeHead.LOADING_UNLOADING)

        assert billed_unloading == money("0")
        assert paid_unloading == money("700.00")
        assert TripMargin(billed=billed_unloading, paid=paid_unloading).margin == money("-700.00")
