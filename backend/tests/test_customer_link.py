"""The link that lets a customer finish their own record.

A customer entered during a morning's bills is a name, a mobile and a town,
because that is what the warehouse has and all it has time for. Everything
that makes a delivery findable — the door, the landmark, the floor, the pin —
belongs to the person who lives there.

So they are sent a link. What these hold is the shape of what that link may
do, because it is handed to somebody outside the company and forwarded on
WhatsApp without a thought:

  * IT REACHES ONE RECORD. Not a login, not a list, not a trip, not a vendor.
  * IT CANNOT MOVE ITSELF. The name must keep matching the vendor's bill, and
    a link that can change the number it was sent to is stolen in one hop.
  * A PIN DROPPED AT THE DOOR IS VERIFIED. Somebody standing there put it
    down, which beats anything the office could type from a town name.
  * IT SURVIVES BEING USED. People remember the landmark an hour later;
    burning the token on first use turns a correction into a phone call.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.tables(
    "users",
    "roles",
    "role_capabilities",
    "role_screens",
    "vendors",
    "consignees",
)


@pytest.fixture()
def customer(client, auth):
    """A customer as the day sheet leaves them: a name, a mobile, a town."""
    res = client.post(
        "/api/consignees",
        json={"name": "Hafrin", "phone": "9812300002", "city": "Kottayam"},
        headers=auth,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _link(client, auth, customer) -> dict:
    res = client.post(f"/api/consignees/{customer}/details-link", headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _token(link: dict) -> str:
    return link["url"].rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Minting it
# ---------------------------------------------------------------------------


def test_the_office_gets_a_link_and_a_message_to_send_with_it(client, customer, auth):
    """Forty of these go out in a morning. Nobody composes a sentence each time."""
    link = _link(client, auth, customer)

    assert "/my-details/" in link["url"]
    assert link["customer_name"] == "Hafrin"
    assert link["phone"] == "9812300002"
    assert link["url"] in link["whatsapp_text"]
    assert "Hafrin" in link["whatsapp_text"]
    assert link["completed_at"] is None


def test_asking_again_replaces_the_old_link(client, customer, auth):
    """Pressing it twice means the first one went to a wrong number."""
    first = _token(_link(client, auth, customer))
    second = _token(_link(client, auth, customer))

    assert first != second
    assert client.get(f"/api/my-details/{first}").status_code == 404
    assert client.get(f"/api/my-details/{second}").status_code == 200


def test_the_existing_link_can_be_read_without_minting_a_new_one(client, customer, auth):
    """Chasing somebody up must not invalidate the link they are holding."""
    minted = _token(_link(client, auth, customer))

    again = client.get(f"/api/consignees/{customer}/details-link", headers=auth)
    assert again.status_code == 200
    assert _token(again.json()) == minted


def test_a_customer_nobody_has_written_to_has_no_link(client, customer, auth):
    res = client.get(f"/api/consignees/{customer}/details-link", headers=auth)
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# What the customer sees and can do
# ---------------------------------------------------------------------------


def test_the_page_needs_no_login(client, customer, auth):
    token = _token(_link(client, auth, customer))

    res = client.get(f"/api/my-details/{token}")
    assert res.status_code == 200
    assert res.json()["name"] == "Hafrin"


def test_it_shows_nothing_but_their_own_record(client, customer, auth):
    """No vendor, no trip, no driver, no other customer."""
    token = _token(_link(client, auth, customer))
    body = client.get(f"/api/my-details/{token}").json()

    assert set(body) == {
        "name",
        "type",
        "phone",
        "contact_person",
        "address",
        "city",
        "pincode",
        "landmark",
        "delivery_notes",
        "latitude",
        "longitude",
        "already_completed",
        "company_name",
    }


def test_what_they_fill_in_reaches_the_record(client, customer, auth):
    token = _token(_link(client, auth, customer))

    res = client.post(
        f"/api/my-details/{token}",
        json={
            "address": "Shop 4, MC Road",
            "landmark": "Opposite the bus stand",
            "pincode": "686001",
            "contact_person": "Mathew",
            "delivery_notes": "Side shutter after 6pm",
        },
    )
    assert res.status_code == 200, res.text

    mine = next(
        c for c in client.get("/api/consignees", headers=auth).json() if c["id"] == customer
    )
    assert mine["address"] == "Shop 4, MC Road"
    assert mine["contact_person"] == "Mathew"
    assert mine["landmark"] == "Opposite the bus stand"
    assert mine["pincode"] == "686001"


def test_a_pin_dropped_at_the_door_is_trusted(client, customer, auth):
    token = _token(_link(client, auth, customer))

    client.post(
        f"/api/my-details/{token}",
        json={"latitude": 9.591, "longitude": 76.522},
    )

    mine = next(
        c for c in client.get("/api/consignees", headers=auth).json() if c["id"] == customer
    )
    assert mine["geo_confidence"] == "VERIFIED"


def test_they_cannot_rename_themselves(client, customer, auth):
    """The name has to keep matching the vendor's bill."""
    token = _token(_link(client, auth, customer))

    client.post(f"/api/my-details/{token}", json={"name": "Somebody Else"})

    mine = next(
        c for c in client.get("/api/consignees", headers=auth).json() if c["id"] == customer
    )
    assert mine["name"] == "Hafrin"


def test_they_cannot_move_the_link_to_another_number(client, customer, auth):
    """It was sent to that mobile. A link that can change it is stolen once."""
    token = _token(_link(client, auth, customer))

    client.post(f"/api/my-details/{token}", json={"phone": "9999999999"})

    mine = next(
        c for c in client.get("/api/consignees", headers=auth).json() if c["id"] == customer
    )
    assert mine["phone"] == "9812300002"


def test_the_link_still_works_after_they_have_used_it(client, customer, auth):
    """People remember the landmark an hour later."""
    token = _token(_link(client, auth, customer))

    client.post(f"/api/my-details/{token}", json={"address": "Shop 4"})
    again = client.post(f"/api/my-details/{token}", json={"landmark": "Near the temple"})

    assert again.status_code == 200
    assert again.json()["already_completed"] is True
    assert again.json()["landmark"] == "Near the temple"


def test_an_expired_link_says_so(client, customer, auth):
    from app.db.session import SessionLocal
    from app.models.consignee import Consignee

    token = _token(_link(client, auth, customer))

    db = SessionLocal()
    try:
        row = db.get(Consignee, customer)
        row.details_token_expires_at = datetime.now().astimezone() - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    res = client.get(f"/api/my-details/{token}")
    assert res.status_code == 404
    assert "expired" in res.json()["detail"].lower()


def test_a_made_up_token_reaches_nothing(client):
    assert client.get("/api/my-details/not-a-real-token").status_code == 404


def test_a_retired_customers_link_stops_working(client, customer, auth):
    token = _token(_link(client, auth, customer))
    client.delete(f"/api/consignees/{customer}", headers=auth)

    assert client.get(f"/api/my-details/{token}").status_code == 404


# ---------------------------------------------------------------------------
# The list of records still waiting
# ---------------------------------------------------------------------------


def test_customers_missing_an_address_or_a_pin_are_listed(client, customer, auth):
    """Invisible on a screen sorted by name, and they are the deliveries that
    will go wrong."""
    rows = client.get("/api/consignees-incomplete", headers=auth).json()

    mine = next(c for c in rows if c["id"] == customer)
    assert mine["has_address"] is False
    assert mine["has_pin"] is False
    assert mine["link_sent_at"] is None


def test_the_list_records_that_a_link_went_out(client, customer, auth):
    _link(client, auth, customer)

    mine = next(
        c
        for c in client.get("/api/consignees-incomplete", headers=auth).json()
        if c["id"] == customer
    )
    assert mine["link_sent_at"] is not None
    assert mine["completed_at"] is None


def test_a_finished_customer_drops_off_the_list(client, customer, auth):
    token = _token(_link(client, auth, customer))
    client.post(
        f"/api/my-details/{token}",
        json={"address": "Shop 4, MC Road", "latitude": 9.591, "longitude": 76.522},
    )

    rows = client.get("/api/consignees-incomplete", headers=auth).json()
    assert customer not in [c["id"] for c in rows]


def test_the_warehouse_can_send_these_links(client, customer):
    """It is his customer and his delivery that goes wrong without it."""
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.user import User

    db = SessionLocal()
    try:
        user = User(
            full_name="Warehouse",
            phone="9000000401",
            role=UserRole.WAREHOUSE_ADMIN,
            hashed_password=hash_password("x"),
            is_active=True,
        )
        db.add(user)
        db.commit()
        headers = {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}
    finally:
        db.close()

    res = client.post(f"/api/consignees/{customer}/details-link", headers=headers)
    assert res.status_code == 200, res.text
