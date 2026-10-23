"""Making a login for somebody who is not Target Express.

The roles existed and nothing could create one. A vendor, a vehicle owner or
an owner-driver could only be set up by writing rows into the database by
hand, which is not a thing anybody should have to do to onboard a customer.

What these hold is the pairing between a role and who it belongs to, because
that pairing is the entire security boundary and it is wrong in two
directions:

  * AN OUTSIDE LOGIN WITH NO TIE reaches nothing. It signs in to a screen
    that says the account is not set up — our mistake arriving as their
    problem — so it is refused at creation instead.
  * AN OFFICE LOGIN WITH A TIE is worse, because nothing in the office
    scopes a query by it. It would be a restriction that looks enforced and
    is not.

And an owner-driver gets a driver record whether or not anybody remembers to
make one, because without it his app signs in, shows no trips and looks
broken.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.tables(
    "users",
    "roles",
    "role_capabilities",
    "role_screens",
    "vendors",
    "vendor_divisions",
    "vehicle_owners",
    "vehicles",
    "drivers",
)


@pytest.fixture()
def parties(client, auth):
    """A vendor and a vehicle owner to hang logins off."""
    from app.db.session import SessionLocal
    from app.models.fleet import VehicleOwner
    from app.models.vendor import Vendor

    db = SessionLocal()
    try:
        vendor = Vendor(name="Godrej", is_active=True)
        owner = VehicleOwner(name="Ibrahim Haji", phone="9846000001", is_active=True)
        db.add_all([vendor, owner])
        db.commit()
        return {"vendor": str(vendor.id), "owner": str(owner.id)}
    finally:
        db.close()


def _create(client, auth, **body):
    base = {
        "full_name": "Somebody",
        "phone": "9000001001",
        "password": "secret123",
        "role": "VENDOR",
    }
    return client.post("/api/auth/users", json={**base, **body}, headers=auth)


# ---------------------------------------------------------------------------
# A vendor login
# ---------------------------------------------------------------------------


def test_a_vendor_login_is_made_against_a_vendor(client, parties, auth):
    res = _create(
        client,
        auth,
        full_name="Godrej Accounts",
        phone="9000001002",
        role="VENDOR",
        vendor_id=parties["vendor"],
    )
    assert res.status_code == 201, res.text

    out = res.json()
    assert out["vendor_id"] == parties["vendor"]
    # Whose login it is, said in the list rather than looked up per row.
    assert out["belongs_to"] == "Godrej"


def test_a_vendor_login_without_a_vendor_is_refused(client, parties, auth):
    """It would reach nothing, and read to them as a broken account."""
    res = _create(client, auth, phone="9000001003", role="VENDOR")

    assert res.status_code == 422
    assert "which vendor" in res.json()["detail"]


def test_a_vendor_that_does_not_exist_is_refused(client, parties, auth):
    import uuid

    res = _create(client, auth, phone="9000001004", role="VENDOR", vendor_id=str(uuid.uuid4()))
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# A vehicle owner, and the man who drives his own lorry
# ---------------------------------------------------------------------------


def test_an_owner_login_is_made_against_an_owner(client, parties, auth):
    res = _create(
        client,
        auth,
        full_name="Ibrahim Haji",
        phone="9846000001",
        role="VEHICLE_OWNER",
        vehicle_owner_id=parties["owner"],
    )
    assert res.status_code == 201, res.text
    assert res.json()["belongs_to"] == "Ibrahim Haji"


def test_an_owner_driver_gets_a_driver_record(client, parties, auth):
    """Without one his app signs in, shows no trips, and looks broken."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.fleet import Driver

    res = _create(
        client,
        auth,
        full_name="Ibrahim Haji",
        phone="9846000001",
        role="OWNER_DRIVER",
        vehicle_owner_id=parties["owner"],
    )
    assert res.status_code == 201, res.text
    user_id = res.json()["id"]

    db = SessionLocal()
    try:
        driver = db.execute(
            select(Driver).where(Driver.user_id == user_id)
        ).scalars().first()
    finally:
        db.close()

    assert driver is not None
    assert driver.name == "Ibrahim Haji"
    # Paid by himself as the owner, not by Target Express.
    assert str(driver.engagement) == "ATTACHED_TO_HIRED_VEHICLE"


def test_an_existing_driver_on_that_number_is_linked_not_duplicated(
    client, parties, auth
):
    """Same man, already on the roster. Two records would split his history."""
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models.fleet import Driver

    db = SessionLocal()
    try:
        db.add(Driver(name="Ibrahim Haji", phone="9846000001", is_active=True))
        db.commit()
    finally:
        db.close()

    res = _create(
        client,
        auth,
        full_name="Ibrahim Haji",
        phone="9846000001",
        role="OWNER_DRIVER",
        vehicle_owner_id=parties["owner"],
    )
    assert res.status_code == 201, res.text

    db = SessionLocal()
    try:
        count = db.scalar(
            select(func.count()).select_from(Driver).where(Driver.phone == "9846000001")
        )
        linked = db.execute(
            select(Driver).where(Driver.phone == "9846000001")
        ).scalars().first()
    finally:
        db.close()

    assert count == 1
    assert str(linked.user_id) == res.json()["id"]


def test_an_owner_driver_without_an_owner_is_refused(client, parties, auth):
    res = _create(client, auth, phone="9000001005", role="OWNER_DRIVER")
    assert res.status_code == 422
    assert "which vehicle owner" in res.json()["detail"]


# ---------------------------------------------------------------------------
# And not the other way round
# ---------------------------------------------------------------------------


def test_an_office_login_cannot_be_tied_to_a_vendor(client, parties, auth):
    """Nothing in the office scopes a query by it, so it would be a
    restriction that looks enforced and is not."""
    res = _create(
        client,
        auth,
        phone="9000001006",
        role="WAREHOUSE_ADMIN",
        vendor_id=parties["vendor"],
    )
    assert res.status_code == 422
    assert "office login" in res.json()["detail"]


def test_an_ordinary_office_login_still_works(client, parties, auth):
    res = _create(client, auth, phone="9000001007", role="WAREHOUSE_ADMIN")
    assert res.status_code == 201, res.text
    assert res.json()["belongs_to"] is None


# ---------------------------------------------------------------------------
# Turning an existing driver into an owner-driver
# ---------------------------------------------------------------------------


def test_a_driver_can_be_promoted_to_an_owner_driver(client, parties, auth):
    """Ibrahim was on the roster as a driver before anybody recorded that
    the lorry is his."""
    created = _create(
        client, auth, full_name="Ibrahim Haji", phone="9846000001", role="DRIVER",
        vendor_id=None,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    res = client.patch(
        f"/api/auth/users/{user_id}",
        json={"role": "OWNER_DRIVER", "vehicle_owner_id": parties["owner"]},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    assert res.json()["belongs_to"] == "Ibrahim Haji"


def test_promoting_without_naming_the_owner_is_refused(client, parties, auth):
    """The role and the tie move together or not at all."""
    created = _create(client, auth, phone="9000001008", role="DRIVER")
    user_id = created.json()["id"]

    res = client.patch(
        f"/api/auth/users/{user_id}", json={"role": "OWNER_DRIVER"}, headers=auth
    )
    assert res.status_code == 422


def test_a_tie_already_on_the_record_counts_when_only_the_role_moves(
    client, parties, auth
):
    """Checked against what the user ENDS UP as, not against the payload —
    half the answer is often already on the record."""
    created = _create(
        client,
        auth,
        full_name="Ibrahim Haji",
        phone="9846000001",
        role="VEHICLE_OWNER",
        vehicle_owner_id=parties["owner"],
    )
    user_id = created.json()["id"]

    res = client.patch(
        f"/api/auth/users/{user_id}", json={"role": "OWNER_DRIVER"}, headers=auth
    )
    assert res.status_code == 200, res.text


def test_the_list_says_whose_login_each_one_is(client, parties, auth):
    _create(
        client,
        auth,
        full_name="Godrej Accounts",
        phone="9000001009",
        role="VENDOR",
        vendor_id=parties["vendor"],
    )

    rows = client.get("/api/auth/users", headers=auth).json()
    godrej = next(r for r in rows if r["phone"] == "9000001009")
    assert godrej["belongs_to"] == "Godrej"
