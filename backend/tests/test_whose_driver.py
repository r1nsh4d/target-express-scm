"""Two kinds of lorry, two kinds of driver.

    A COMPANY LORRY is driven by a company driver. Target Express pays him by
    the kilometre, plus the unloading cash he hands over at the door.

    AN OUTSIDE LORRY belongs to somebody who may drive it himself or may send
    a man. Target Express pays the OWNER for the lorry and what it carried
    in; the man at the wheel is paid by the owner, and what he is paid is not
    our business.

A vehicle has always known whose it is. A driver did not — so Ibrahim's man
and ours looked identical in every list, and "who are Ibrahim's drivers" had
no answer. That question is behind giving one of them a login, and behind an
owner reading what his own lorries did.

`engagement` carried a hint and could not carry the fact: it says a man
drives somebody else's lorry, not WHOSE. One owner with four lorries and
three drivers is ordinary, and that column cannot describe it.

The other thing here is the distinction the assign screen got wrong:
BELONGING TO IBRAHIM AND BEING IBRAHIM ARE DIFFERENT. Only the second changes
who is paid, and both of them are different again from a company driver, for
whom both are empty — which is how "owns this lorry" ended up printed against
every name on an owned vehicle.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.tables(
    "users",
    "roles",
    "role_capabilities",
    "role_screens",
    "vehicle_types",
    "vehicle_owners",
    "vehicles",
    "vehicle_hire_terms",
    "drivers",
    "driver_pay_terms",
    # The owner's home screen counts his month as well as listing his men.
    "freights",
    "freight_legs",
    "settlements",
    "freight_payouts",
    "advances",
)


@pytest.fixture()
def fleet(client, auth):
    """One company lorry, and an owner with two of his own."""
    from app.db.session import SessionLocal
    from app.models.enums import VehicleOwnership
    from app.models.fleet import Vehicle, VehicleOwner

    db = SessionLocal()
    try:
        ibrahim = VehicleOwner(name="Ibrahim Haji", phone="9846000011", is_active=True)
        shaji = VehicleOwner(name="Shaji", phone="9846000012", is_active=True)
        db.add_all([ibrahim, shaji])
        db.flush()

        ours = Vehicle(
            registration_no="KL07CW3317",
            ownership=VehicleOwnership.OWNED,
            lr_next_number=1,
            is_active=True,
        )
        his_one = Vehicle(
            registration_no="KL10AL4477",
            ownership=VehicleOwnership.HIRED,
            owner_id=ibrahim.id,
            lr_next_number=901,
            is_active=True,
        )
        his_two = Vehicle(
            registration_no="KL10AL5588",
            ownership=VehicleOwnership.HIRED,
            owner_id=ibrahim.id,
            lr_next_number=950,
            is_active=True,
        )
        db.add_all([ours, his_one, his_two])
        db.commit()
        return {
            "ibrahim": str(ibrahim.id),
            "shaji": str(shaji.id),
            "ours": str(ours.id),
            "his_one": str(his_one.id),
            "his_two": str(his_two.id),
        }
    finally:
        db.close()


def _driver(client, auth, **body):
    base = {"name": "Somebody", "phone": "9000002001", "create_login": False}
    return client.post("/api/drivers", json={**base, **body}, headers=auth)


def _drivers(client, auth):
    return client.get("/api/drivers", headers=auth).json()


# ---------------------------------------------------------------------------
# Whose man he is
# ---------------------------------------------------------------------------


def test_a_driver_with_no_owner_is_ours(client, fleet, auth):
    res = _driver(client, auth, name="Rajesh K", phone="9000002002")
    assert res.status_code == 201, res.text

    out = res.json()
    assert out["vehicle_owner_id"] is None
    assert out["engagement"] == "OWN_STAFF"


def test_a_driver_can_belong_to_an_owner(client, fleet, auth):
    res = _driver(
        client,
        auth,
        name="Basheer C",
        phone="9000002003",
        vehicle_owner_id=fleet["ibrahim"],
    )
    assert res.status_code == 201, res.text

    out = res.json()
    assert out["vehicle_owner_id"] == fleet["ibrahim"]
    assert out["vehicle_owner_name"] == "Ibrahim Haji"


def test_belonging_to_an_owner_sets_the_engagement(client, fleet, auth):
    """The two said the same thing in two places and could disagree, and the
    one somebody reads is whichever the screen happened to show."""
    out = _driver(
        client, auth, phone="9000002004", vehicle_owner_id=fleet["ibrahim"]
    ).json()

    assert out["engagement"] == "ATTACHED_TO_HIRED_VEHICLE"


def test_an_owner_that_does_not_exist_is_refused(client, fleet, auth):
    import uuid

    res = _driver(client, auth, phone="9000002005", vehicle_owner_id=str(uuid.uuid4()))
    assert res.status_code == 404


def test_one_owner_can_have_several_drivers(client, fleet, auth):
    """Four lorries and three drivers is an ordinary arrangement."""
    for n, name in enumerate(["Basheer C", "Noushad", "Jaleel"]):
        _driver(
            client,
            auth,
            name=name,
            phone=f"900000301{n}",
            vehicle_owner_id=fleet["ibrahim"],
        )

    his = [d for d in _drivers(client, auth) if d["vehicle_owner_id"] == fleet["ibrahim"]]
    assert len(his) == 3


# ---------------------------------------------------------------------------
# Belonging to him, and being him
# ---------------------------------------------------------------------------


def test_a_mans_employer_is_not_the_same_as_being_him(client, fleet, auth):
    """Only the second changes who is paid."""
    out = _driver(
        client,
        auth,
        name="Basheer C",
        phone="9000002006",
        vehicle_owner_id=fleet["ibrahim"],
    ).json()

    assert out["vehicle_owner_id"] == fleet["ibrahim"]
    assert out["is_the_owner"] is False


def test_an_owner_driving_his_own_lorry_is_both(client, fleet, auth):
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.fleet import Driver
    from app.models.user import User

    created = _driver(
        client,
        auth,
        name="Ibrahim Haji",
        phone="9846000011",
        vehicle_owner_id=fleet["ibrahim"],
    ).json()

    db = SessionLocal()
    try:
        user = User(
            full_name="Ibrahim Haji",
            phone="9846000011",
            role=UserRole.OWNER_DRIVER,
            hashed_password=hash_password("x"),
            is_active=True,
            vehicle_owner_id=fleet["ibrahim"],
        )
        db.add(user)
        db.flush()
        db.get(Driver, created["id"]).user_id = user.id
        db.commit()
    finally:
        db.close()

    mine = next(d for d in _drivers(client, auth) if d["id"] == created["id"])
    assert mine["is_the_owner"] is True


def test_a_company_driver_is_neither(client, fleet, auth):
    """Both fields empty, which is what made `null === null` true and printed
    "owns this lorry" against every name on an owned vehicle."""
    created = _driver(client, auth, name="Anil P", phone="9000002007").json()

    mine = next(d for d in _drivers(client, auth) if d["id"] == created["id"])
    assert mine["vehicle_owner_id"] is None
    assert mine["is_the_owner"] is False


# ---------------------------------------------------------------------------
# Moving a man between the two
# ---------------------------------------------------------------------------


def test_a_driver_can_be_moved_to_an_owner(client, fleet, auth):
    """Basheer was on file before anybody recorded whose man he is."""
    created = _driver(client, auth, name="Basheer C", phone="9000002008").json()

    res = client.patch(
        f"/api/drivers/{created['id']}",
        json={"vehicle_owner_id": fleet["ibrahim"], "set_owner": True},
        headers=auth,
    )
    assert res.status_code == 200, res.text

    mine = next(d for d in _drivers(client, auth) if d["id"] == created["id"])
    assert mine["vehicle_owner_name"] == "Ibrahim Haji"
    assert mine["engagement"] == "ATTACHED_TO_HIRED_VEHICLE"


def test_a_driver_can_be_taken_back(client, fleet, auth):
    """Null is a real answer here, which is why it is paired with a flag."""
    created = _driver(
        client, auth, phone="9000002009", vehicle_owner_id=fleet["ibrahim"]
    ).json()

    client.patch(
        f"/api/drivers/{created['id']}",
        json={"vehicle_owner_id": None, "set_owner": True},
        headers=auth,
    )

    mine = next(d for d in _drivers(client, auth) if d["id"] == created["id"])
    assert mine["vehicle_owner_id"] is None
    assert mine["engagement"] == "OWN_STAFF"


def test_editing_a_name_leaves_his_owner_alone(client, fleet, auth):
    """Omitted means unchanged, which is why the flag exists."""
    created = _driver(
        client, auth, phone="9000002010", vehicle_owner_id=fleet["ibrahim"]
    ).json()

    client.patch(
        f"/api/drivers/{created['id']}", json={"name": "Basheer Cheriya"}, headers=auth
    )

    mine = next(d for d in _drivers(client, auth) if d["id"] == created["id"])
    assert mine["vehicle_owner_id"] == fleet["ibrahim"]


# ---------------------------------------------------------------------------
# What the owner sees
# ---------------------------------------------------------------------------


def test_an_owner_sees_his_own_drivers(client, fleet, auth):
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.user import User

    _driver(client, auth, name="Basheer C", phone="9000002011",
            vehicle_owner_id=fleet["ibrahim"])
    _driver(client, auth, name="Somebody Else", phone="9000002012",
            vehicle_owner_id=fleet["shaji"])
    _driver(client, auth, name="Anil P", phone="9000002013")

    db = SessionLocal()
    try:
        user = User(
            full_name="Ibrahim Haji",
            phone="9846000099",
            role=UserRole.VEHICLE_OWNER,
            hashed_password=hash_password("x"),
            is_active=True,
            vehicle_owner_id=fleet["ibrahim"],
        )
        db.add(user)
        db.commit()
        headers = {
            "Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"
        }
    finally:
        db.close()

    home = client.get("/api/owner/home", headers=headers).json()

    assert [d["name"] for d in home["drivers"]] == ["Basheer C"]
    # And his lorries, both of them.
    assert len(home["vehicles"]) == 2
