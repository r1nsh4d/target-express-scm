"""The enquiry, end to end: landing page form -> database -> admin screen.

This is the one path in the product where a stranger on the internet writes to
the database, and the one where a missed row is a lost customer. So it is tested
through the real app over HTTP rather than by calling functions: that is what
catches a wrong table name, a route that was never registered, or a response
model that cannot serialise what the ORM returns.
"""

import pytest

pytestmark = pytest.mark.tables("users", "enquiries")


GOOD = {
    "company_name": "Anand Agencies",
    "contact_name": "Rahul Menon",
    "phone": "+91 98470 12345",
    "email": "rahul@anandagencies.in",
    "goods_type": "Furniture",
    "origin_city": "Kochi",
    "monthly_volume": "about 400 boxes",
    "message": "We move furniture to dealers across north Kerala.",
}


# ---------------------------------------------------------------------------
# The public form
# ---------------------------------------------------------------------------


def test_anyone_can_submit_without_signing_in(client):
    """The whole point: a vendor who has never heard of us can reach the desk."""
    res = client.post("/api/public/enquiries", json=GOOD)
    assert res.status_code == 201, res.text
    assert res.json()["ok"] is True
    assert "call you" in res.json()["message"]


def test_only_the_three_essentials_are_required(client):
    """An enquiry form that interrogates people gets abandoned."""
    res = client.post(
        "/api/public/enquiries",
        json={"company_name": "Beena Stores", "contact_name": "Beena", "phone": "9847012346"},
    )
    assert res.status_code == 201, res.text


def test_a_company_with_no_name_is_refused(client):
    res = client.post(
        "/api/public/enquiries",
        json={"company_name": "", "contact_name": "Beena", "phone": "9847012346"},
    )
    assert res.status_code == 422


def test_an_unreachable_phone_is_refused(client):
    """The phone is the only way the office can answer this."""
    res = client.post(
        "/api/public/enquiries",
        json={"company_name": "Beena Stores", "contact_name": "Beena", "phone": "----"},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# The admin screen
# ---------------------------------------------------------------------------


def test_the_office_sees_what_was_submitted(client, auth):
    client.post("/api/public/enquiries", json=GOOD)

    res = client.get("/api/enquiries", headers=auth)
    assert res.status_code == 200, res.text

    rows = res.json()
    assert len(rows) == 1

    row = rows[0]
    assert row["company_name"] == "Anand Agencies"
    assert row["contact_name"] == "Rahul Menon"
    assert row["phone"] == "+91 98470 12345"
    assert row["goods_type"] == "Furniture"
    assert row["origin_city"] == "Kochi"
    assert row["monthly_volume"] == "about 400 boxes"
    assert row["status"] == "NEW"
    # The id has to come back as a string or every screen 500s on it.
    assert isinstance(row["id"], str)


def test_the_list_needs_a_login(client):
    """It holds other businesses' contact details."""
    assert client.get("/api/enquiries").status_code == 401


def test_newest_first(client, auth):
    """An enquiry two days old is already cold, so the fresh one is on top.

    The timestamps are set directly: three HTTP posts land inside the same
    second, and SQLite stores seconds, so they would all tie and prove nothing.
    """
    from datetime import datetime, timedelta

    from app.db.session import SessionLocal
    from app.models.enquiry import Enquiry

    for name in ("First Traders", "Second Traders", "Third Traders"):
        client.post(
            "/api/public/enquiries",
            json={"company_name": name, "contact_name": "Xavier", "phone": "9847012345"},
        )

    db = SessionLocal()
    now = datetime.now()
    ages = {"First Traders": 2, "Second Traders": 1, "Third Traders": 0}
    for row in db.query(Enquiry).all():
        row.created_at = now - timedelta(days=ages[row.company_name])
    db.commit()
    db.close()

    rows = client.get("/api/enquiries", headers=auth).json()
    assert [r["company_name"] for r in rows] == [
        "Third Traders",
        "Second Traders",
        "First Traders",
    ]


def test_the_order_does_not_shuffle_between_refreshes(client, auth):
    """Three arriving in the same second must still come back in one order, or
    the list reorders itself under the person working it."""
    for i in range(3):
        client.post(
            "/api/public/enquiries",
            json={"company_name": f"Co {i}", "contact_name": "Xavier", "phone": "9847012345"},
        )

    first = [r["id"] for r in client.get("/api/enquiries", headers=auth).json()]
    second = [r["id"] for r in client.get("/api/enquiries", headers=auth).json()]
    assert first == second
    assert len(first) == 3


# ---------------------------------------------------------------------------
# Working the list
# ---------------------------------------------------------------------------


def test_marking_one_called_records_when(client, auth):
    """The answer to 'did anyone actually ring them back, and when'."""
    client.post("/api/public/enquiries", json=GOOD)
    row = client.get("/api/enquiries", headers=auth).json()[0]
    assert row["contacted_at"] is None

    res = client.patch(
        f"/api/enquiries/{row['id']}",
        json={"status": "CONTACTED", "internal_note": "Rang, wants a rate card for furniture"},
        headers=auth,
    )
    assert res.status_code == 200, res.text

    updated = res.json()
    assert updated["status"] == "CONTACTED"
    assert updated["contacted_at"] is not None
    assert "rate card" in updated["internal_note"]


def test_the_pipeline_runs_through_to_won(client, auth):
    client.post("/api/public/enquiries", json=GOOD)
    enquiry_id = client.get("/api/enquiries", headers=auth).json()[0]["id"]

    for stage in ("CONTACTED", "QUOTED", "WON"):
        res = client.patch(f"/api/enquiries/{enquiry_id}", json={"status": stage}, headers=auth)
        assert res.status_code == 200
        assert res.json()["status"] == stage


def test_filtering_by_stage(client, auth):
    client.post(
        "/api/public/enquiries",
        json={"company_name": "A Co", "contact_name": "Anil", "phone": "9847012345"},
    )
    client.post(
        "/api/public/enquiries",
        json={"company_name": "B Co", "contact_name": "Biju", "phone": "9847012346"},
    )
    rows = client.get("/api/enquiries", headers=auth).json()
    client.patch(f"/api/enquiries/{rows[0]['id']}", json={"status": "WON"}, headers=auth)

    won = client.get("/api/enquiries?status_filter=WON", headers=auth).json()
    assert len(won) == 1
    assert won[0]["status"] == "WON"

    still_new = client.get("/api/enquiries?status_filter=NEW", headers=auth).json()
    assert len(still_new) == 1


# ---------------------------------------------------------------------------
# Spam
# ---------------------------------------------------------------------------


def test_a_filled_honeypot_is_accepted_and_hidden(client, auth):
    """Accepted, because a bot that gets a 422 learns to retry without the
    honeypot. Hidden, because the office should never see it."""
    res = client.post(
        "/api/public/enquiries",
        json={
            "company_name": "Cheap Pills Inc",
            "contact_name": "Bot",
            "phone": "9999999999",
            "website": "http://spam.example",
        },
    )
    assert res.status_code == 201
    assert res.json()["ok"] is True

    assert client.get("/api/enquiries", headers=auth).json() == []


def test_spam_is_kept_rather_than_discarded(client, auth):
    """The row is the evidence when a burst needs investigating."""
    client.post(
        "/api/public/enquiries",
        json={
            "company_name": "Cheap Pills Inc",
            "contact_name": "Bot",
            "phone": "9999999999",
            "website": "http://spam.example",
        },
    )
    flagged = client.get("/api/enquiries?status_filter=SPAM", headers=auth).json()
    assert len(flagged) == 1
    assert flagged[0]["company_name"] == "Cheap Pills Inc"


def test_a_genuine_enquiry_is_not_flagged(client, auth):
    client.post("/api/public/enquiries", json=GOOD)
    rows = client.get("/api/enquiries", headers=auth).json()
    assert len(rows) == 1
    assert rows[0]["status"] == "NEW"


def test_the_rate_limit_stops_a_flood(client):
    """Five per ten minutes. The sixth is refused rather than stored."""
    for i in range(5):
        res = client.post(
            "/api/public/enquiries",
            json={"company_name": f"Co {i}", "contact_name": "Xavier", "phone": "9847012345"},
        )
        assert res.status_code == 201, f"attempt {i + 1}: {res.text}"

    sixth = client.post(
        "/api/public/enquiries",
        json={"company_name": "Co 6", "contact_name": "Xavier", "phone": "9847012345"},
    )
    assert sixth.status_code == 429
