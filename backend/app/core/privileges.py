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

    # Read the office screens: freights, bills, labels, reports.
    OFFICE_VIEW = "office.view"
    # Create and change the day's work: bills, freights, loading, dispatch.
    OPERATIONS = "operations.manage"
    # Invoices, settlements, advances, expenses, money in.
    MONEY = "money.manage"
    # Vendors, rates, vehicles, drivers, customers, users, enquiries.
    ADMIN = "admin.manage"
    # The driver's own app. Never granted alongside the others — a person is
    # out on the road or in the office, and a login that is both is a login
    # being shared.
    DRIVE = "drive"


CAPABILITIES: dict[str, str] = {
    Capability.OFFICE_VIEW: "See the office screens",
    Capability.OPERATIONS: "Enter bills, build freights, dispatch",
    Capability.MONEY: "Invoices, settlements, advances and expenses",
    Capability.ADMIN: "Vendors, rates, vehicles, drivers and users",
    Capability.DRIVE: "Use the driver app",
}


# Exactly what each built-in role could already reach, written out.
#
# Derived from the groupings the guards used before roles were configurable:
#   ADMIN_ROLES       = SUPER_ADMIN, OPS_ADMIN
#   WAREHOUSE_ROLES   = ADMIN_ROLES + WAREHOUSE_ADMIN
#   ACCOUNTS_ROLES    = SUPER_ADMIN, ACCOUNTS
#   BACK_OFFICE_ROLES = all five office roles
#
# Nothing here grants anything new. If a test that passed before this file
# fails after it, this table is wrong and not the test.
SYSTEM_ROLE_CAPABILITIES: dict[UserRole, set[str]] = {
    UserRole.SUPER_ADMIN: {
        Capability.OFFICE_VIEW,
        Capability.OPERATIONS,
        Capability.MONEY,
        Capability.ADMIN,
    },
    UserRole.OPS_ADMIN: {
        Capability.OFFICE_VIEW,
        Capability.OPERATIONS,
        Capability.ADMIN,
    },
    UserRole.WAREHOUSE_ADMIN: {Capability.OFFICE_VIEW, Capability.OPERATIONS},
    UserRole.ACCOUNTS: {Capability.OFFICE_VIEW, Capability.MONEY},
    UserRole.STAKEHOLDER: {Capability.OFFICE_VIEW},
    UserRole.DRIVER: {Capability.DRIVE},
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
    ("consignees", "Customers", Capability.ADMIN),
    ("vehicles", "Vehicles", Capability.ADMIN),
    ("market-vehicles", "Market vehicles", Capability.ADMIN),
    ("drivers", "Drivers", Capability.ADMIN),
    ("labour", "Loading crew", Capability.ADMIN),
    ("categories", "Goods categories", Capability.ADMIN),
    ("rate-cards", "Rate cards", Capability.ADMIN),
    ("unloading-rates", "Unloading rates", Capability.ADMIN),
    ("invoices", "Vendor invoices", Capability.MONEY),
    ("money-in", "Money in", Capability.MONEY),
    ("settlements", "Settlements", Capability.MONEY),
    ("advances", "Advances", Capability.MONEY),
    ("reports", "Reports", Capability.OFFICE_VIEW),
    ("expenses", "Expenses", Capability.MONEY),
    ("enquiries", "Enquiries", Capability.ADMIN),
    ("users", "Users", Capability.ADMIN),
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
