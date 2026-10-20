"""Roles somebody can make, instead of six compiled into the application.

The thing these tests guard above everything else is that the six built-in
roles behave exactly as they did before any of this existed. The capability
table is a TRANSLATION of the groupings the guards already used, and if a
test that passed before it fails after it, the table is wrong and not the
test.

The second thing is the point of the feature: a role nobody anticipated — a
branch manager who sees freights and invoices but not settlements — reaches
what it was given and nothing else.
"""

import pytest

from app.core.privileges import (
    CAPABILITIES,
    SCREENS,
    SYSTEM_ROLE_CAPABILITIES,
    Capability,
    capabilities_for_role,
    screens_for,
)
from app.models.enums import UserRole

pytestmark = pytest.mark.tables("users", "roles", "role_capabilities", "role_screens")


# ---------------------------------------------------------------------------
# The translation
# ---------------------------------------------------------------------------


def test_every_built_in_role_is_described():
    """A role with no entry would silently lose every permission it had."""
    for role in UserRole:
        assert role in SYSTEM_ROLE_CAPABILITIES, role


@pytest.mark.parametrize(
    "role,expected",
    [
        (
            UserRole.SUPER_ADMIN,
            {
                Capability.OFFICE_VIEW,
                Capability.OPERATIONS,
                Capability.FLEET,
                Capability.ADVANCES,
                Capability.MONEY,
                Capability.REPORTS,
                Capability.ADMIN,
            },
        ),
        (
            UserRole.OPS_ADMIN,
            {
                Capability.OFFICE_VIEW,
                Capability.OPERATIONS,
                Capability.FLEET,
                Capability.ADVANCES,
                Capability.REPORTS,
                Capability.ADMIN,
            },
        ),
        (
            UserRole.WAREHOUSE_ADMIN,
            {
                Capability.OFFICE_VIEW,
                Capability.OPERATIONS,
                Capability.FLEET,
                Capability.ADVANCES,
            },
        ),
        (
            UserRole.ACCOUNTS,
            {
                Capability.OFFICE_VIEW,
                Capability.ADVANCES,
                Capability.MONEY,
                Capability.REPORTS,
            },
        ),
        (UserRole.STAKEHOLDER, {Capability.OFFICE_VIEW, Capability.REPORTS}),
        (UserRole.DRIVER, {Capability.DRIVE}),
    ],
)
def test_each_role_holds_what_it_is_meant_to(role, expected):
    """Written out by hand, because a mapping derived from the code it guards
    proves nothing.

    This began as a faithful translation of the role groupings the guards used
    before roles were configurable — ADMIN_ROLES, WAREHOUSE_ROLES and the
    rest. Two of those groupings turned out to be wrong about the warehouse:

      * customers, drivers and vehicles sat behind ADMIN beside the rate
        cards, so a warehouse admin could not add the dealer his own freight
        was going to;
      * Reports needed only `office.view`, which every office role has, so he
        could read the company's revenue and margin.

    FLEET and REPORTS split those apart, and ADVANCES was pulled out of MONEY
    because the driver asking for diesel money is standing at his counter.
    """
    assert capabilities_for_role(role) == expected


def test_a_stakeholder_still_cannot_touch_money():
    assert Capability.MONEY not in capabilities_for_role(UserRole.STAKEHOLDER)
    assert Capability.OPERATIONS not in capabilities_for_role(UserRole.STAKEHOLDER)


def test_accounts_still_cannot_build_a_freight():
    assert Capability.OPERATIONS not in capabilities_for_role(UserRole.ACCOUNTS)


def test_a_warehouse_admin_still_cannot_reach_the_money():
    assert Capability.MONEY not in capabilities_for_role(UserRole.WAREHOUSE_ADMIN)
    assert Capability.ADMIN not in capabilities_for_role(UserRole.WAREHOUSE_ADMIN)


def test_a_driver_has_nothing_in_the_office(client):
    """A login that is both a driver and an administrator is a login being
    shared, and the moment one exists nobody can say who recorded a
    delivery."""
    assert capabilities_for_role(UserRole.DRIVER) == {Capability.DRIVE}


def test_every_screen_names_a_real_capability():
    """A screen needing a capability nobody can hold is a screen nobody can
    open, and nothing would say why."""
    for key, label, needs in SCREENS:
        assert needs in CAPABILITIES, f"{key} needs {needs}, which does not exist"


def test_screens_follow_from_capabilities():
    only_money = screens_for({Capability.MONEY})
    assert "invoices" in only_money
    assert "settlements" in only_money
    assert "vendors" not in only_money, "money does not imply the masters"


# ---------------------------------------------------------------------------
# The built-in roles, as rows
# ---------------------------------------------------------------------------


def test_the_six_are_seeded_on_first_listing(client, auth):
    res = client.get("/api/roles", headers=auth)
    assert res.status_code == 200, res.text

    roles = res.json()
    assert {r["base_role"] for r in roles if r["is_system"]} == {r.value for r in UserRole}
    assert all(r["capabilities"] for r in roles)


def test_seeding_twice_does_not_duplicate(client, auth):
    client.get("/api/roles", headers=auth)
    roles = client.get("/api/roles", headers=auth).json()
    assert len(roles) == len(UserRole)


def test_a_built_in_role_cannot_be_deleted(client, auth):
    """It is referenced by name in code and reseeded on every deploy."""
    roles = client.get("/api/roles", headers=auth).json()
    accounts = next(r for r in roles if r["base_role"] == "ACCOUNTS")

    res = client.delete(f"/api/roles/{accounts['id']}", headers=auth)
    assert res.status_code == 409
    assert "built in" in res.json()["detail"]


def test_a_built_in_roles_permissions_cannot_be_edited(client, auth):
    """Editing Super Admin to drop admin.manage is how somebody locks
    themselves out of the screen they would need to undo it."""
    roles = client.get("/api/roles", headers=auth).json()
    sa = next(r for r in roles if r["base_role"] == "SUPER_ADMIN")

    res = client.patch(
        f"/api/roles/{sa['id']}",
        json={"name": sa["name"], "capabilities": [Capability.OFFICE_VIEW], "screens": []},
        headers=auth,
    )
    assert res.status_code == 409
    assert "built in" in res.json()["detail"]


def test_a_built_in_role_can_be_renamed(client, auth):
    """"Ops Admin" to "Operations Desk" is presentation, and somebody who
    renames it should not find it renamed back on the next deploy."""
    roles = client.get("/api/roles", headers=auth).json()
    ops = next(r for r in roles if r["base_role"] == "OPS_ADMIN")

    res = client.patch(
        f"/api/roles/{ops['id']}",
        json={
            "name": "Operations Desk",
            "capabilities": ops["capabilities"],
            "screens": ops["screens"],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Operations Desk"

    again = client.get("/api/roles", headers=auth).json()
    assert any(r["name"] == "Operations Desk" for r in again), "the reseed renamed it back"


# ---------------------------------------------------------------------------
# A role nobody anticipated
# ---------------------------------------------------------------------------


def _second_user_on(role_id: str) -> None:
    """Put somebody else on this role.

    Not the caller: giving the admin a role without admin.manage correctly
    takes their admin away, and the next request in the test is an admin
    one. Which is the feature working, and a confusing way to test it.
    """
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole as _UR
    from app.models.user import User

    db = SessionLocal()
    db.add(
        User(
            full_name="Branch Person",
            phone="9000000111",
            role=_UR.OPS_ADMIN,
            hashed_password=hash_password("x"),
            is_active=True,
            role_id=role_id,
        )
    )
    db.commit()
    db.close()


BRANCH = {
    "name": "Branch Manager · Kannur",
    "description": "Sees the work and the invoices, not the settlements",
    "capabilities": [Capability.OFFICE_VIEW, Capability.OPERATIONS],
    "screens": ["freights", "consignments", "labels", "dashboard"],
}


def test_a_role_can_be_made(client, auth):
    res = client.post("/api/roles", json=BRANCH, headers=auth)
    assert res.status_code == 201, res.text

    body = res.json()
    assert body["is_system"] is False
    assert set(body["capabilities"]) == {Capability.OFFICE_VIEW, Capability.OPERATIONS}


def test_two_roles_cannot_share_a_name(client, auth):
    client.post("/api/roles", json=BRANCH, headers=auth)
    res = client.post("/api/roles", json={**BRANCH, "name": "branch manager · kannur"}, headers=auth)
    assert res.status_code == 409


def test_a_screen_beyond_the_capabilities_is_not_granted(client, auth):
    """An item in the rail with a 403 behind it is worse than no item."""
    res = client.post(
        "/api/roles",
        json={**BRANCH, "screens": ["freights", "settlements", "users"]},
        headers=auth,
    )
    body = res.json()
    assert "freights" in body["screens"]
    assert "settlements" not in body["screens"], "money screen on a role without money"
    assert "users" not in body["screens"]


def test_a_driver_role_cannot_also_be_an_administrator(client, auth):
    res = client.post(
        "/api/roles",
        json={
            "name": "Driver who also does the books",
            "capabilities": [Capability.DRIVE, Capability.MONEY],
            "screens": [],
        },
        headers=auth,
    )
    assert res.status_code == 422
    assert "second login" in res.json()["detail"]


def test_an_unknown_capability_is_refused(client, auth):
    res = client.post(
        "/api/roles",
        json={**BRANCH, "capabilities": ["freights.delete_everything"]},
        headers=auth,
    )
    assert res.status_code == 422


def test_a_role_in_use_cannot_be_deleted(client, auth):
    """Deleting it would null their role_id and silently drop those people
    back to whatever their base enum says."""
    role = client.post("/api/roles", json=BRANCH, headers=auth).json()
    _second_user_on(role["id"])

    res = client.delete(f"/api/roles/{role['id']}", headers=auth)
    assert res.status_code == 409
    assert "Move them" in res.json()["detail"]


def test_an_unused_role_can_be_deleted(client, auth):
    role = client.post("/api/roles", json=BRANCH, headers=auth).json()
    assert client.delete(f"/api/roles/{role['id']}", headers=auth).status_code == 204


# ---------------------------------------------------------------------------
# What it changes for the person signed in
# ---------------------------------------------------------------------------


def test_a_custom_role_decides_what_the_rail_shows(client, auth):
    from sqlalchemy import select

    from app.core.security import create_access_token
    from app.db.session import SessionLocal
    from app.models.user import User

    role = client.post("/api/roles", json=BRANCH, headers=auth).json()
    _second_user_on(role["id"])

    db = SessionLocal()
    them = db.execute(select(User).where(User.phone == "9000000111")).scalar_one()
    token = create_access_token(str(them.id), them.role)
    db.close()

    access = client.get(
        "/api/me/access", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert access["role_name"] == "Branch Manager · Kannur"
    assert set(access["capabilities"]) == {Capability.OFFICE_VIEW, Capability.OPERATIONS}
    assert "settlements" not in access["screens"]


def test_a_custom_role_loses_what_it_was_not_given(client, auth):
    """The point of the feature: the role decides, not the enum."""
    from sqlalchemy import select

    from app.core.security import create_access_token
    from app.db.session import SessionLocal
    from app.models.user import User

    role = client.post("/api/roles", json=BRANCH, headers=auth).json()
    _second_user_on(role["id"])

    db = SessionLocal()
    them = db.execute(select(User).where(User.phone == "9000000111")).scalar_one()
    token = create_access_token(str(them.id), them.role)
    db.close()

    # Money is not on this role, and Money in is a money endpoint. Their base
    # enum says OPS_ADMIN, which would not have reached it either — but a
    # role that DID grant money would, and that is what the custom role is
    # deciding here.
    res = client.get("/api/money-in", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_without_a_custom_role_the_built_in_one_still_decides(client, auth):
    access = client.get("/api/me/access", headers=auth).json()
    assert access["role_name"] == "Super Admin"
    assert Capability.MONEY in access["capabilities"]


def test_roles_are_for_administrators_only(client):
    assert client.get("/api/roles").status_code == 401


# ---------------------------------------------------------------------------
# Creating a user against a role
# ---------------------------------------------------------------------------


def test_a_user_is_created_against_a_role(client, auth):
    """The point of the whole thing: make a role, then make people on it."""
    role = client.post("/api/roles", json=BRANCH, headers=auth).json()

    res = client.post(
        "/api/auth/users",
        json={
            "full_name": "Branch Person",
            "phone": "9000000222",
            "password": "secret123",
            "role": "OPS_ADMIN",
            "role_id": role["id"],
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text

    body = res.json()
    assert body["role_id"] == role["id"]
    assert body["role_name"] == "Branch Manager · Kannur"


def test_the_role_name_shows_in_the_list(client, auth):
    """A user list showing the enum where a custom role applies tells the
    administrator the opposite of what they configured."""
    role = client.post("/api/roles", json=BRANCH, headers=auth).json()
    client.post(
        "/api/auth/users",
        json={
            "full_name": "Branch Person",
            "phone": "9000000223",
            "password": "secret123",
            "role": "OPS_ADMIN",
            "role_id": role["id"],
        },
        headers=auth,
    )

    rows = client.get("/api/auth/users", headers=auth).json()
    them = next(u for u in rows if u["phone"] == "9000000223")
    assert them["role_name"] == "Branch Manager · Kannur"


def test_an_existing_user_can_be_moved_onto_a_role(client, auth):
    role = client.post("/api/roles", json=BRANCH, headers=auth).json()
    made = client.post(
        "/api/auth/users",
        json={
            "full_name": "Someone",
            "phone": "9000000224",
            "password": "secret123",
            "role": "STAKEHOLDER",
        },
        headers=auth,
    ).json()

    res = client.patch(
        f"/api/auth/users/{made['id']}", json={"role_id": role["id"]}, headers=auth
    )
    assert res.status_code == 200, res.text
    assert res.json()["role_name"] == "Branch Manager · Kannur"


def test_moving_onto_a_role_takes_the_base_role_with_it(client, auth):
    """A role deleted out from under somebody leaves them on their enum, so
    the enum has to be something sensible rather than whatever they used to
    be."""
    roles = client.get("/api/roles", headers=auth).json()
    accounts = next(r for r in roles if r["base_role"] == "ACCOUNTS")

    made = client.post(
        "/api/auth/users",
        json={
            "full_name": "Someone",
            "phone": "9000000225",
            "password": "secret123",
            "role": "STAKEHOLDER",
        },
        headers=auth,
    ).json()

    res = client.patch(
        f"/api/auth/users/{made['id']}", json={"role_id": accounts["id"]}, headers=auth
    )
    assert res.json()["role"] == "ACCOUNTS", "the base did not follow the role"


def test_somebody_can_be_taken_off_a_custom_role(client, auth):
    role = client.post("/api/roles", json=BRANCH, headers=auth).json()
    made = client.post(
        "/api/auth/users",
        json={
            "full_name": "Someone",
            "phone": "9000000226",
            "password": "secret123",
            "role": "STAKEHOLDER",
            "role_id": role["id"],
        },
        headers=auth,
    ).json()

    res = client.patch(f"/api/auth/users/{made['id']}", json={"clear_role": True}, headers=auth)
    assert res.status_code == 200, res.text
    assert res.json()["role_id"] is None
    assert res.json()["role_name"] is None


def test_a_user_cannot_be_put_on_a_role_that_does_not_exist(client, auth):
    res = client.post(
        "/api/auth/users",
        json={
            "full_name": "Someone",
            "phone": "9000000227",
            "password": "secret123",
            "role": "STAKEHOLDER",
            "role_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=auth,
    )
    assert res.status_code == 404
