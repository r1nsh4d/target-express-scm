"""Domain enumerations.

Values are stored as strings in Postgres so the database stays readable and new
members can be added without a migration dance.
"""

from enum import StrEnum


class UserRole(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    OPS_ADMIN = "OPS_ADMIN"
    WAREHOUSE_ADMIN = "WAREHOUSE_ADMIN"
    ACCOUNTS = "ACCOUNTS"
    DRIVER = "DRIVER"
    STAKEHOLDER = "STAKEHOLDER"


class ConsigneeType(StrEnum):
    RETAIL_CUSTOMER = "RETAIL_CUSTOMER"
    DISTRIBUTION_CENTER = "DISTRIBUTION_CENTER"


class GeoConfidence(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    APPROXIMATE = "APPROXIMATE"
    VERIFIED = "VERIFIED"


class VehicleOwnership(StrEnum):
    OWNED = "OWNED"
    HIRED = "HIRED"


class HireRateBasis(StrEnum):
    PER_KM = "PER_KM"
    PER_TRIP = "PER_TRIP"
    PER_DAY = "PER_DAY"


class DriverEngagement(StrEnum):
    OWN_STAFF = "OWN_STAFF"
    ATTACHED_TO_HIRED_VEHICLE = "ATTACHED_TO_HIRED_VEHICLE"


class UnloadingBasis(StrEnum):
    """How unloading is billed to the vendor. NOT how the driver is paid."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    ACTUAL = "ACTUAL"
    PER_POINT = "PER_POINT"
    PER_BOX = "PER_BOX"
    # Furniture: each article has its own ground-floor rate plus a per-floor
    # climb charge. A chair at 50 delivered to the 4th floor at 10 a floor
    # unloads at 90.
    PER_ITEM_FLOOR = "PER_ITEM_FLOOR"


class ChargeHead(StrEnum):
    """The heads a trip earns under, and pays out under.

    The same three heads drive both sides of a trip: what the vendor is billed,
    and what the driver or the vehicle owner is paid. The amounts differ - the
    billed side comes from the vendor rate card, the paid side from the driver's
    pay terms or the vehicle's hire terms - but the heads are shared, which is
    what makes margin readable head by head.
    """

    TRANSPORTATION = "TRANSPORTATION"      # base trip + extra distance
    LOADING_UNLOADING = "LOADING_UNLOADING"
    POINT_INCENTIVE = "POINT_INCENTIVE"    # points beyond those included
    TOLL = "TOLL"                          # pass-through
    DETENTION = "DETENTION"                # pass-through
    # Local porters who control unloading at certain markets and godowns. They
    # are not Target Express's crew and not on the unloading rate sheet - they
    # are a cash demand made at the point, which the driver pays and the vendor
    # reimburses. Held as its own head precisely because it is NOT unloading:
    # mixing the two would make the unloading sheet look wrong, and a vendor
    # querying "why is unloading higher this month" could not be answered.
    COOLIE = "COOLIE"                      # pass-through
    OTHER = "OTHER"


class PayeeType(StrEnum):
    """Who is actually paid for a leg.

    An owned vehicle pays its driver. A rented vehicle pays the vehicle's owner,
    because the hire is a vehicle arrangement rather than a driver one - the
    owner settles with his own driver. Both names still print on the settlement
    document.
    """

    DRIVER = "DRIVER"
    VEHICLE_OWNER = "VEHICLE_OWNER"


class SettlementStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class AdvanceStatus(StrEnum):
    OUTSTANDING = "OUTSTANDING"
    PART_RECOVERED = "PART_RECOVERED"
    RECOVERED = "RECOVERED"
    WRITTEN_OFF = "WRITTEN_OFF"


class BoxStatus(StrEnum):
    SORTED = "SORTED"
    LABELLED = "LABELLED"
    LOADED = "LOADED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    SHORT_AT_LOADING = "SHORT_AT_LOADING"
    DAMAGED = "DAMAGED"
    NOT_DELIVERED = "NOT_DELIVERED"
    RETURNED_TO_WAREHOUSE = "RETURNED_TO_WAREHOUSE"


class ConsignmentStatus(StrEnum):
    RECEIVED = "RECEIVED"
    SORTED = "SORTED"
    ASSIGNED = "ASSIGNED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    PART_DELIVERED = "PART_DELIVERED"
    RETURNED = "RETURNED"


class FreightStatus(StrEnum):
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    LOADING = "LOADING"
    DISPATCHED = "DISPATCHED"
    IN_TRANSIT = "IN_TRANSIT"
    COMPLETED = "COMPLETED"
    BILLED = "BILLED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class FreightPointStatus(StrEnum):
    PENDING = "PENDING"
    LOADED = "LOADED"
    ARRIVED = "ARRIVED"
    DELIVERED = "DELIVERED"
    PART_DELIVERED = "PART_DELIVERED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class LegChangeReason(StrEnum):
    INITIAL = "INITIAL"
    BREAKDOWN = "BREAKDOWN"
    ACCIDENT = "ACCIDENT"
    DRIVER_UNAVAILABLE = "DRIVER_UNAVAILABLE"
    OTHER = "OTHER"


class ExpenseType(StrEnum):
    UNLOADING = "UNLOADING"
    LOADING = "LOADING"
    FUEL = "FUEL"
    TOLL = "TOLL"
    PARKING = "PARKING"
    FOOD = "FOOD"
    REPAIR = "REPAIR"
    ADVANCE = "ADVANCE"
    DETENTION = "DETENTION"
    OTHER = "OTHER"


class PaidBy(StrEnum):
    DRIVER = "DRIVER"
    COMPANY = "COMPANY"


class EntryMode(StrEnum):
    SELF = "SELF"
    ADMIN_ON_BEHALF = "ADMIN_ON_BEHALF"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class InvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    SENT = "SENT"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class LocationChangeStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AUTO_APPROVED = "AUTO_APPROVED"


class EnquiryStatus(StrEnum):
    """A business enquiry from the public site, through the office's hands."""

    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUOTED = "QUOTED"
    WON = "WON"
    LOST = "LOST"
    SPAM = "SPAM"


class MarketVehicleStanding(StrEnum):
    """Whether a market supplier can be relied on.

    Three states, not a star rating. The only question an admin asks at 7am
    with a load waiting is "can I call this one", and a 3.5 does not answer it.
    """

    UNTRIED = "UNTRIED"      # in the book, never used
    RELIABLE = "RELIABLE"    # turned up, would call again
    AVOID = "AVOID"          # did not turn up, or caused a problem


class UnloadingShareBasis(StrEnum):
    """Which pot the driver's unloading share is a percentage OF.

    The unloading charge is split: a share to the driver, the rest kept by
    Target Express. But "a share of what" has two honest answers, and they pay
    the driver different money:

      BILLED_TO_VENDOR  a share of what the vendor is charged. The vendor pays
                        900, the driver's 70% is 630, Target Express keeps 270.
                        The split is a true percentage split of one pot, which
                        is how the arrangement is usually described.

      PAID_AT_POINT     a share of the cash that actually went out at the
                        points. At 100% this is a straight reimbursement of
                        money the driver laid out of his own pocket, and what
                        Target Express keeps is whatever the vendor was billed
                        above that.

    PAID_AT_POINT is the default, and deliberately so. On a spare-parts run the
    vendor is billed NOTHING for unloading while the driver still hands cash to
    the labourers. A percentage of zero is zero, so defaulting to the billed
    basis would quietly leave that driver out of pocket for the whole amount.

    For the same reason, the billed basis carries a floor: the driver is never
    paid less than the cash he actually laid out. See compute_driver_payout.

    Stored per driver and snapshotted onto the payout, because a driver moved
    from one arrangement to the other must not have last month's settlement
    silently recomputed.
    """

    PAID_AT_POINT = "PAID_AT_POINT"
    BILLED_TO_VENDOR = "BILLED_TO_VENDOR"
