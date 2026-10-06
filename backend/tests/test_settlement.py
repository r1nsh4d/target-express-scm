"""The per-trip money cycle for a rented vehicle.

Target Express pays the vehicle owner only. The owner draws an advance when the
vehicle leaves, the trip runs, and the advance is set against what the trip
earned to give the balance that closes the account.
"""

from decimal import Decimal

from app.models.enums import ChargeHead, HireRateBasis, PayeeType, VehicleOwnership
from app.services.payout import HireRates, LegFacts, compute_leg_payout
from app.services.rating import money
from app.services.settlement import TripAccount, head_totals

HIRE = HireRates(
    rate_basis=HireRateBasis.PER_KM,
    rate_value=Decimal("13.00"),
    minimum_km_per_trip=150,
)


def owner_account(gross: str, drawn: str, recovered: str) -> TripAccount:
    return TripAccount(
        payee_type=PayeeType.VEHICLE_OWNER,
        payee_id="owner-1",
        payee_name="Ibrahim Haji",
        driver_names=["Rajesh K"],
        gross=money(gross),
        advance_drawn=money(drawn),
        advance_recovered=money(recovered),
    )


class TestRentedTripSplitsBetweenOwnerAndDriver:
    """The hire settles to the owner; the unloading cash goes to the driver,
    who splits it with the cleaner and labourers."""

    def test_hire_goes_to_the_owner(self):
        payout = compute_leg_payout(
            VehicleOwnership.HIRED,
            LegFacts(km=561, points=6, unloading_paid=Decimal("900")),
            hire_rates=HIRE,
        )
        assert payout.payee_type == PayeeType.VEHICLE_OWNER
        assert payout.total_for(PayeeType.VEHICLE_OWNER) == money("7293.00")  # 561 x 13

    def test_unloading_goes_to_the_driver(self):
        payout = compute_leg_payout(
            VehicleOwnership.HIRED,
            LegFacts(km=561, points=6, unloading_paid=Decimal("900")),
            hire_rates=HIRE,
        )
        assert payout.total_for(PayeeType.DRIVER) == money("900.00")

    def test_a_driver_on_a_rented_vehicle_earns_no_hire(self):
        """He is the owner's employee for the driving; only the unloading cash
        passes through him."""
        payout = compute_leg_payout(
            VehicleOwnership.HIRED, LegFacts(km=561), hire_rates=HIRE
        )
        assert payout.total_for(PayeeType.DRIVER) == money("0")


class TestAdvanceAndClose:
    def test_balance_is_what_remains_after_the_advance(self):
        account = owner_account(gross="8193.00", drawn="5000.00", recovered="5000.00")
        assert account.balance_payable == money("3193.00")
        assert account.advance_carried_forward == money("0")
        assert not account.is_closed

    def test_a_fully_covered_trip_closes_at_zero(self):
        account = owner_account(gross="5000.00", drawn="5000.00", recovered="5000.00")
        assert account.balance_payable == money("0")
        assert account.is_closed

    def test_no_advance_means_the_whole_amount_is_payable(self):
        account = owner_account(gross="8193.00", drawn="0", recovered="0")
        assert account.balance_payable == money("8193.00")

    def test_an_advance_bigger_than_the_trip_carries_forward(self):
        """Not an error: the excess is recovered from the owner's next trip."""
        account = owner_account(gross="3000.00", drawn="5000.00", recovered="3000.00")
        assert account.balance_payable == money("0")
        assert account.advance_carried_forward == money("2000.00")
        assert account.is_closed

    def test_partial_recovery_leaves_both_a_balance_and_a_carry_forward(self):
        account = owner_account(gross="8193.00", drawn="9000.00", recovered="8193.00")
        assert account.balance_payable == money("0")
        assert account.advance_carried_forward == money("807.00")


class TestDocumentNamesBothParties:
    def test_owner_is_the_payee_and_the_driver_is_still_listed(self):
        account = owner_account(gross="8193.00", drawn="5000.00", recovered="5000.00")
        assert account.payee_type == PayeeType.VEHICLE_OWNER
        assert account.payee_name == "Ibrahim Haji"
        assert account.driver_names == ["Rajesh K"]


class TestHeadTotals:
    def test_every_head_prints_even_when_zero(self):
        account = owner_account(gross="8193.00", drawn="0", recovered="0")
        account.by_head = {
            str(ChargeHead.TRANSPORTATION): money("7293.00"),
            str(ChargeHead.LOADING_UNLOADING): money("900.00"),
        }
        totals = head_totals(account)

        assert totals[str(ChargeHead.TRANSPORTATION)] == money("7293.00")
        assert totals[str(ChargeHead.LOADING_UNLOADING)] == money("900.00")
        assert totals[str(ChargeHead.POINT_INCENTIVE)] == money("0")
        assert totals[str(ChargeHead.DETENTION)] == money("0")

    def test_heads_are_in_a_fixed_order(self):
        account = owner_account(gross="0", drawn="0", recovered="0")
        assert list(head_totals(account)) == [
            str(ChargeHead.TRANSPORTATION),
            str(ChargeHead.LOADING_UNLOADING),
            str(ChargeHead.POINT_INCENTIVE),
            str(ChargeHead.TOLL),
            str(ChargeHead.DETENTION),
            str(ChargeHead.OTHER),
        ]
