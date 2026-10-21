"""What a role is allowed to do.

The application had six fixed roles compiled into an enum, and every guard in
it asked "is this person one of these roles". That is fine until the day
somebody wants a branch manager in Kannur who can see freights and invoices but
not settlements — a shape nobody anticipated, and one that previously required
a developer.

So a role is now a set of privileges, and the six built-in ones are expressed
in exactly the privileges they already had. That mapping is a TRANSLATION, not
a redesign: Warehouse Admin can do today precisely what Warehouse Admin could
do yesterday, and the tests that prove it were passing before this file
existed.

Two layers, deliberately, because they are enforced in different places and
pretending otherwise would be a lie told by a tick box:

  CAPABILITIES are enforced on the server, by the route guards. There are few
  of them because there are few distinct guards — inventing a "Freights:
  delete" tick that no endpoint consults would be a switch wired to nothing.

  SCREENS decide what appears in the navigation. A role with the money
  capability but without the Settlements screen still cannot reach it by
  accident, and the server would still allow it if asked directly. That is
  worth saying plainly rather than implying a lock that is not there.
"""

from __future__ import annotations

from app.models.enums import UserRole


class Capability:
    """What the server actually checks. One per distinct route guard."""

    # Read the day's work: freights, bills, labels, the dashboard.
    OFFICE_VIEW = "office.view"
    # Create and change it: bills, freights, loading, dispatch, returns.
    OPERATIONS = "operations.manage"
    # Customers, drivers, vehicles and the loading crew.
    #
    # Split out of ADMIN, because the warehouse runs on these. A warehouse
    # admin building tomorrow's freights needs to add the dealer who rang this
    # morning and the lorry that turned up; making him wait for somebody with
    # the keys to the rate cards is how the real list ends up in a notebook.
    # What he still cannot touch is what anything is CHARGED at.
    FLEET = "fleet.manage"
    # Hand cash to a driver before a settlement, and record its recovery.
    #
    # Its own capability rather than part of MONEY, because it is a warehouse
    # act — the driver is standing at the counter asking for diesel money —
    # while invoicing a vendor is not. Both still land in the same ledger.
    ADVANCES = "advances.manage"
    # Invoices, settlements, expenses, money in.
    MONEY = "money.manage"
    # What the business earned: revenue, margin, what each driver and lorry
    # brought in. Separate from MONEY because reading the figures and moving
    # them are different jobs — an owner reads, an accounts clerk moves.
    REPORTS = "reports.view"
    # Vendors, rate cards, users and roles. The commercial terms and the keys.
    ADMIN = "admin.manage"
    # The driver's own app. Never granted alongside the others — a person is
    # out on the road or in the office, and a login that is both is a login
    # being shared.
    DRIVE = "drive"

    # --- logins that belong to somebody outside the company --------------- #
    #
    # These are not smaller versions of an office role. An office login with
    # fewer screens still sees the whole business through them; these see one
    # vendor's work, or one owner's lorries, and the filtering is done in the
    # query rather than by hiding a menu. Granting one of these alongside an
    # office capability would be a category error, so nothing does.
    VENDOR_PORTAL = "vendor.portal"
    OWNER_PORTAL = "owner.portal"


CAPABILITIES: dict[str, str] = {
    Capability.OFFICE_VIEW: "See the day's freights and bills",
    Capability.OPERATIONS: "Enter bills, build freights, dispatch",
    Capability.FLEET: "Add and edit customers, drivers and vehicles",
    Capability.ADVANCES: "Hand an advance to a driver",
    Capability.MONEY: "Invoices, settlements, expenses and money in",
    Capability.REPORTS: "See what the business earned",
    Capability.ADMIN: "Vendors, rate cards, users and roles",
    Capability.DRIVE: "Use the driver app",
    Capability.VENDOR_PORTAL: "A vendor's own freights, rates and bills",
    Capability.OWNER_PORTAL: "A vehicle owner's earnings and advances",
}


# What each built-in role holds.
#
# This began as a faithful translation of the role groupings the guards used
# before roles were configurable. Two of those groupings turned out to be
# wrong about the warehouse, and the warehouse is where the work happens:
#
#   A WAREHOUSE ADMIN COULD NOT ADD A CUSTOMER. Customers, drivers and
#   vehicles all sat behind ADMIN alongside the rate cards. So the man
#   building tomorrow's freights could enter the bills but not the dealer
#   they were going to, and the real list drifted into a notebook. He has
#   FLEET now. He still cannot see or set what anything is charged at.
#
#   A WAREHOUSE ADMIN COULD SEE THE REPORTS. Revenue, margin, what each
#   driver earned — all of it, because Reports only needed office.view. The
#   dashboard's earnings tiles the same way. Neither is his business, and
#   both are now behind REPORTS.
#
# He can also hand out an advance, because the driver asking for diesel money
# is standing at his counter.
SYSTEM_ROLE_CAPABILITIES: dict[UserRole, set[str]] = {
    UserRole.SUPER_ADMIN: {
        Capability.OFFICE_VIEW,
        Capability.OPERATIONS,
        Capability.FLEET,
        Capability.ADVANCES,
        Capability.MONEY,
        Capability.REPORTS,
        Capability.ADMIN,
    },
    UserRole.OPS_ADMIN: {
        Capability.OFFICE_VIEW,
        Capability.OPERATIONS,
        Capability.FLEET,
        Capability.ADVANCES,
        Capability.REPORTS,
        Capability.ADMIN,
    },
    UserRole.WAREHOUSE_ADMIN: {
        Capability.OFFICE_VIEW,
        Capability.OPERATIONS,
        Capability.FLEET,
        Capability.ADVANCES,
    },
    UserRole.ACCOUNTS: {
        Capability.OFFICE_VIEW,
        Capability.ADVANCES,
        Capability.MONEY,
        Capability.REPORTS,
    },
    # Reads the figures, moves nothing.
    UserRole.STAKEHOLDER: {Capability.OFFICE_VIEW, Capability.REPORTS},
    UserRole.DRIVER: {Capability.DRIVE},
    UserRole.VENDOR: {Capability.VENDOR_PORTAL},
    UserRole.VEHICLE_OWNER: {Capability.OWNER_PORTAL},
    # Runs the trip AND is paid for it, because he is both parties.
    #
    # The note on DRIVE says it is never granted alongside the others, and
    # that is about OFFICE capabilities: a login that both drives and invoices
    # is a login being shared. This is a different thing. An owner-driver is
    # one man with one lorry, and the money he is looking at is his own.
    #
    # What it does mean is that whoever holds this login sees that owner's
    # money. If he hands it to a man he employs, he has handed over his own
    # figures — which is his decision to make about his own business, and is
    # worth saying out loud rather than discovering.
    UserRole.OWNER_DRIVER: {Capability.DRIVE, Capability.OWNER_PORTAL},
}


# Every screen in the navigation, and the capability it needs to be of any use.
#
# The screen list on a role controls what appears in the rail. The capability
# is what the server enforces — so hiding a screen is tidiness, and removing a
# capability is security. Both are useful and they are not the same thing.
SCREENS: list[tuple[str, str, str]] = [
    # (key, label, capability it needs)
    ("dashboard", "Dashboard", Capability.OFFICE_VIEW),
    ("day-sheet", "Day sheet", Capability.OPERATIONS),
    ("freights", "Freights", Capability.OFFICE_VIEW),
    ("consignments", "Consignments", Capability.OFFICE_VIEW),
    ("presets", "Saved routes", Capability.OPERATIONS),
    ("labels", "Sorting & labels", Capability.OFFICE_VIEW),
    ("returns", "Returns", Capability.OPERATIONS),
    ("vendors", "Vendors", Capability.ADMIN),
    ("consignees", "Customers", Capability.FLEET),
    ("vehicles", "Vehicles", Capability.FLEET),
    ("market-vehicles", "Market vehicles", Capability.FLEET),
    ("drivers", "Drivers", Capability.FLEET),
    ("labour", "Loading crew", Capability.FLEET),
    ("categories", "Goods categories", Capability.ADMIN),
    ("rate-cards", "Rate cards", Capability.ADMIN),
    ("unloading-rates", "Unloading rates", Capability.ADMIN),
    ("invoices", "Vendor invoices", Capability.MONEY),
    ("money-in", "Money in", Capability.MONEY),
    ("settlements", "Settlements", Capability.MONEY),
    ("advances", "Advances", Capability.ADVANCES),
    ("reports", "Reports", Capability.REPORTS),
    ("expenses", "Expenses", Capability.MONEY),
    ("enquiries", "Enquiries", Capability.ADMIN),
    ("users", "Users", Capability.ADMIN),
    # Missing until now, which is exactly why a warehouse admin could open
    # Roles: nothing filtered a screen the table had never heard of.
    ("roles", "Roles", Capability.ADMIN),
    ("guide", "User guide", Capability.OFFICE_VIEW),
]

SCREEN_KEYS = {key for key, _, _ in SCREENS}


def screens_for(capabilities: set[str]) -> set[str]:
    """Every screen a set of capabilities could reach.

    The default screen list for a new role, and the ceiling for any role: a
    screen whose capability is missing is not offered, because a tick that
    puts an item in the rail and a 403 behind it is worse than no tick.
    """
    return {key for key, _, needs in SCREENS if needs in capabilities}


def capabilities_for_role(role: UserRole) -> set[str]:
    return set(SYSTEM_ROLE_CAPABILITIES.get(role, set()))
