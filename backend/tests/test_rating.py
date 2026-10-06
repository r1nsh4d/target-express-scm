"""Rating engine tests, anchored on real Target Express invoices.

Source documents:
  - 191/2026-27/022  Godrej Appliance Spare, 29 trips, 03-07-2026 to 15-07-2026
  - 191/2026-27/023  Godrej OCP

Both bill on the same terms: base 1867 covering 60 km and 3 points, then 17 per
extra km and 175 per extra point, with toll, unloading and detention passed
through at actuals.
"""

from decimal import Decimal

import pytest

from app.services.rating import (
    FreightCharge,
    RateTerms,
    TripFacts,
    calculate_freight_charge,
    money,
)

# The terms recovered from both Godrej invoices.
GODREJ = RateTerms(
    base_trip_amount=Decimal("1867.00"),
    included_km=60,
    extra_km_rate=Decimal("17.00"),
    included_points=3,
    extra_point_rate=Decimal("175.00"),
)


def charge(km: int, points: int, **extras) -> FreightCharge:
    return calculate_freight_charge(GODREJ, TripFacts(km=km, points=points, **extras))


class TestVerifiedInvoiceLines:
    """Lines read off invoice 191/2026-27/022 and reproduced exactly."""

    # (trip_no, destination, points, km, toll, printed line total)
    LINES = [
        ("Y26005704", "TVM", 11, 560, "0", "11767.00"),
        ("Y26005771", "Kottayam", 6, 345, "0", "7237.00"),
        ("Y26005698", "Kozhikode", 4, 412, "280", "8306.00"),
        ("Y26005701", "Malappuram", 7, 368, "145", "7948.00"),
        ("Y26005822", "Thrissur", 6, 182, "105", "4571.00"),
        ("Y26005823", "Palakkad", 7, 345, "260", "7672.00"),
        ("Y26005892", "Kasaragod", 7, 900, "290", "17137.00"),
        ("Y26005903", "Kozhikode", 4, 486, "280", "9564.00"),
        ("Y26006013", "Kollam", 3, 388, "0", "7443.00"),
        ("Y26006108", "Palakkad", 9, 352, "260", "8141.00"),
        ("Y26006109", "TVM", 11, 944, "290", "18585.00"),
        ("Y26006140", "Palakkad", 2, 270, "260", "5697.00"),
    ]

    @pytest.mark.parametrize("trip_no,destination,points,km,toll,expected", LINES)
    def test_line_total_matches_invoice(self, trip_no, destination, points, km, toll, expected):
        result = charge(km, points, toll=Decimal(toll))
        assert result.line_total == money(expected), (
            f"{trip_no} {destination}: expected {expected}, got {result.line_total}"
        )

    def test_extra_km_component(self):
        """900 km to Kasaragod: 840 chargeable km at 17."""
        result = charge(900, 7)
        assert result.extra_km == 840
        assert result.extra_km_amount == money("14280.00")

    def test_extra_point_component(self):
        """12 points is the busiest trip on the invoice: 9 chargeable at 175."""
        result = charge(449, 12)
        assert result.extra_points == 9
        assert result.extra_point_amount == money("1575.00")


class TestInvoiceControlTotals:
    """The column totals printed on invoice 191/2026-27/022.

    The per-trip split below is synthetic - it only has to reproduce the
    invoice's own totals (29 trips, 15,151 km, 139 chargeable extra points,
    5,280 toll, 1,540 additional unloading). Because no trip falls under the
    included thresholds, the arithmetic is linear and the aggregate is exact.
    """

    TRIP_COUNT = 29
    TOTAL_KM = 15_151
    TOTAL_EXTRA_POINTS = 139
    TOTAL_TOLL = Decimal("5280.00")
    TOTAL_UNLOADING_ADDITIONAL = Decimal("1540.00")

    # As printed on the invoice.
    EXPECTED_BASE = money("54143.00")
    EXPECTED_EXTRA_KM = 13_411
    EXPECTED_EXTRA_KM_AMOUNT = money("227987.00")
    EXPECTED_EXTRA_POINT_AMOUNT = money("24325.00")
    EXPECTED_GRAND_TOTAL = money("313275.00")

    def build_trips(self) -> list[TripFacts]:
        # 28 trips at 500 km, one carrying the remainder.
        kms = [500] * 28 + [self.TOTAL_KM - 500 * 28]
        # 27 trips with 5 extra points, 2 with 2 extra: 27*5 + 2*2 = 139.
        extra_points = [5] * 27 + [2, 2]
        assert sum(extra_points) == self.TOTAL_EXTRA_POINTS

        trips = []
        for i, (km, extra) in enumerate(zip(kms, extra_points, strict=True)):
            trips.append(
                TripFacts(
                    km=km,
                    points=GODREJ.included_points + extra,
                    toll=self.TOTAL_TOLL if i == 0 else Decimal("0"),
                    unloading_additional=(
                        self.TOTAL_UNLOADING_ADDITIONAL if i == 0 else Decimal("0")
                    ),
                )
            )
        return trips

    def test_trip_set_matches_invoice_inputs(self):
        trips = self.build_trips()
        assert len(trips) == self.TRIP_COUNT
        assert sum(t.km for t in trips) == self.TOTAL_KM

    def test_column_totals(self):
        charges = [calculate_freight_charge(GODREJ, t) for t in self.build_trips()]

        assert money(sum(c.base_amount for c in charges)) == self.EXPECTED_BASE
        assert sum(c.extra_km for c in charges) == self.EXPECTED_EXTRA_KM
        assert money(sum(c.extra_km_amount for c in charges)) == self.EXPECTED_EXTRA_KM_AMOUNT
        assert sum(c.extra_points for c in charges) == self.TOTAL_EXTRA_POINTS
        assert (
            money(sum(c.extra_point_amount for c in charges))
            == self.EXPECTED_EXTRA_POINT_AMOUNT
        )
        assert money(sum(c.toll for c in charges)) == self.TOTAL_TOLL

    def test_grand_total(self):
        charges = [calculate_freight_charge(GODREJ, t) for t in self.build_trips()]
        assert money(sum(c.line_total for c in charges)) == self.EXPECTED_GRAND_TOTAL


class TestGodrejOcpInvoice:
    """Invoice 191/2026-27/023 runs a different division on the same terms."""

    # (km, expected extra km amount)
    DISTANCE_LINES = [(360, "5100.00"), (538, "8126.00"), (513, "7701.00"),
                      (399, "5763.00"), (802, "12614.00")]

    @pytest.mark.parametrize("km,expected", DISTANCE_LINES)
    def test_extra_km_amount(self, km, expected):
        assert charge(km, points=3).extra_km_amount == money(expected)


class TestPointRulesVaryPerVendor:
    """Both the threshold and the per-point rate are per-vendor settings.

    'Points' here are the freight's delivery points - the stops on the trip.
    """

    VENDORS = {
        # name: (base_point_charge, included_points, extra_point_rate)
        "Godrej": ("0", 3, "175"),
        "Vendor B": ("500", 3, "100"),
        "Vendor C": ("0", 5, "120"),
        "Vendor D": ("750", 8, "90"),
    }

    def terms(self, name: str) -> RateTerms:
        slab, included, rate = self.VENDORS[name]
        return RateTerms(
            base_trip_amount=Decimal("0"),
            included_km=0,
            extra_km_rate=Decimal("0"),
            included_points=included,
            extra_point_rate=Decimal(rate),
            base_point_charge=Decimal(slab),
        )

    @pytest.mark.parametrize(
        "vendor,points,expected",
        [
            # Godrej: nothing for the first 3, then 175 each.
            ("Godrej", 3, "0"),
            ("Godrej", 5, "350"),
            ("Godrej", 10, "1225"),
            # Vendor B: 500 covers 3, then 100 each.
            ("Vendor B", 3, "500"),
            ("Vendor B", 5, "700"),
            ("Vendor B", 10, "1200"),
            # Vendor C: a higher threshold, nothing until the 6th stop.
            ("Vendor C", 3, "0"),
            ("Vendor C", 5, "0"),
            ("Vendor C", 10, "600"),
            # Vendor D: a big slab and a high threshold.
            ("Vendor D", 3, "750"),
            ("Vendor D", 5, "750"),
            ("Vendor D", 10, "930"),
        ],
    )
    def test_same_trip_bills_differently_per_vendor(self, vendor, points, expected):
        result = calculate_freight_charge(self.terms(vendor), TripFacts(km=0, points=points))
        assert result.extra_point_amount == money(expected)

    def test_threshold_and_rate_are_independent_settings(self):
        ten_points = TripFacts(km=0, points=10)
        amounts = {
            name: calculate_freight_charge(self.terms(name), ten_points).extra_point_amount
            for name in self.VENDORS
        }
        # Four vendors, four different answers for the identical 10-point trip.
        assert len(set(amounts.values())) == 4


class TestPointSlab:
    """A vendor may charge a fixed amount for the first N points and a rate
    thereafter, instead of folding the allowance into the trip base."""

    SLAB = RateTerms(
        base_trip_amount=Decimal("0"),
        included_km=0,
        extra_km_rate=Decimal("0"),
        included_points=3,
        extra_point_rate=Decimal("100"),
        base_point_charge=Decimal("500"),
    )

    def test_seven_points_bills_the_slab_plus_the_extras(self):
        """500 for the first 3, then 4 extra at 100 = 900."""
        result = calculate_freight_charge(self.SLAB, TripFacts(km=0, points=7))
        assert result.extra_point_amount == money("900.00")

    def test_at_the_included_count_only_the_slab_is_charged(self):
        result = calculate_freight_charge(self.SLAB, TripFacts(km=0, points=3))
        assert result.extra_point_amount == money("500.00")

    def test_below_the_included_count_still_charges_the_slab(self):
        result = calculate_freight_charge(self.SLAB, TripFacts(km=0, points=1))
        assert result.extra_point_amount == money("500.00")

    def test_trace_names_the_slab(self):
        result = calculate_freight_charge(self.SLAB, TripFacts(km=0, points=7))
        assert "500 for the first 3 + 4 extra x 100 = 900.00" in " | ".join(result.trace)

    def test_godrej_is_unaffected_because_its_slab_is_zero(self):
        """Godrej folds the point allowance into the 1867 trip base, so the
        slab field is zero and the invoices still reconcile."""
        assert GODREJ.base_point_charge == Decimal("0")
        result = charge(345, 7)
        assert result.extra_point_amount == money("700.00")


class TestBoundaries:
    def test_short_trip_is_not_charged_negative_distance(self):
        result = charge(40, points=3)
        assert result.extra_km == 0
        assert result.extra_km_amount == money("0")
        assert result.line_total == money("1867.00")

    def test_fewer_points_than_included_is_not_charged_negative(self):
        result = charge(60, points=1)
        assert result.extra_points == 0
        assert result.extra_point_amount == money("0")
        assert result.line_total == money("1867.00")

    def test_exact_threshold_charges_nothing_extra(self):
        result = charge(60, points=3)
        assert result.line_total == money("1867.00")

    def test_pass_through_charges_are_added_untouched(self):
        result = charge(
            60,
            3,
            toll=Decimal("105"),
            unloading=Decimal("500"),
            unloading_additional=Decimal("300"),
            detention=Decimal("250"),
        )
        assert result.line_total == money("3022.00")


class TestCalculationTrace:
    """Every line has to explain itself; vendor queries are answered from this."""

    def test_trace_shows_the_distance_working(self):
        result = charge(360, points=3)
        joined = " | ".join(result.trace)
        assert "360 km - 60 km included = 300 km x 17.00 = 5100.00" in joined

    def test_trace_ends_with_the_line_total(self):
        result = charge(182, 6, toll=Decimal("105"))
        assert result.trace[-1] == "Line total: 4571.00"


class TestRateTermsSnapshot:
    """A freight freezes its rates at dispatch, so old invoices reprint intact."""

    def test_snapshot_round_trip(self):
        snapshot = GODREJ.to_snapshot()
        restored = RateTerms.from_snapshot(snapshot)
        assert restored == GODREJ

    def test_charge_from_restored_terms_is_identical(self):
        facts = TripFacts(km=944, points=11, toll=Decimal("290"))
        restored = RateTerms.from_snapshot(GODREJ.to_snapshot())
        assert (
            calculate_freight_charge(restored, facts).line_total
            == calculate_freight_charge(GODREJ, facts).line_total
        )
