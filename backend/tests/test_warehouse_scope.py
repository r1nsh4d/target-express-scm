"""What a warehouse admin can and cannot reach.

He runs the day: bills in, freights built, stickers printed, drivers assigned,
returns scanned. Two things were wrong about where his edges were, and both
were invisible until somebody logged in as him and looked.

HE COULD NOT ADD A CUSTOMER, A DRIVER OR A LORRY. Those sat behind the same
capability as the rate cards, so the man building tomorrow's freights could
enter the bills but not the dealer they were going to. The real list ends up
in a notebook, and after that the application is decoration.

HE COULD READ THE COMPANY'S EARNINGS. Reports needed only `office.view`,
which every office role has — so revenue, margin and what every driver earned
were one click from the screen he lives on. The per-freight money view was the
same. Neither is his business.

And Roles had no entry in the screen table at all, so nothing filtered it out
of his rail; the page it opened then sat on a spinner forever, because its own
check was "loading, or no data" and the data was never coming — the API had
refused it. A permanent spinner is the worst way to say no: it reads as a
broken application rather than a closed door.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.tables(
    "users",
    "roles",
    "role_capabilities",
    "role_screens",
    "goods_categories",
    "vendors",
    "vendor_divisions",
    "vendor_warehouses",
    "consignees",
    "vehicle_types",
    "vehicle_owners",
    "vehicles",
    "drivers",
    "driver_pay_terms",
    "labour",
    "rate_cards",
    "unloading_item_rates",
    "freights",
    "freight_points",
    "freight_legs",
    "consignments",
    "boxes",
    "trip_expenses",
    "vendor_invoices",
    "vendor_invoice_lines",
    "settlements",
    "freight_payouts",
    "advances",
)


def _login(role_name: str, phone: str):
    """A signed-in user on one of the built-in roles."""
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.user import User

    db = SessionLocal()
    try:
        user = User(
            full_name=role_name.title(),
            phone=phone,
            role=UserRole[role_name],
            hashed_password=hash_password("x"),
            is_active=True,
        )
        db.add(user)
        db.commit()
        return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}
    finally:
        db.close()


@pytest.fixture()
def warehouse(client):
    return _login("WAREHOUSE_ADMIN", "9000000201")


@pytest.fixture()
def stakeholder(client):
    return _login("STAKEHOLDER", "9000000202")


# ---------------------------------------------------------------------------
# What he needs
# ---------------------------------------------------------------------------


def test_he_can_add_a_customer(client, warehouse):
    """A dealer who rang this morning has to go on today's freight."""
    res = client.post(
        "/api/consignees",
        json={"name": "Kottayam Furniture Mart", "city": "Kottayam"},
        headers=warehouse,
    )
    assert res.status_code == 201, res.text


def test_he_can_add_a_driver_and_a_lorry(client, warehouse):
    """Both turn up at the gate without warning."""
    assert (
        client.post(
            "/api/vehicles", json={"registration_no": "KL07AA1111"}, headers=warehouse
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/drivers",
            json={"name": "Shaji", "phone": "9000000301", "create_login": False},
            headers=warehouse,
        ).status_code
        == 201
    )


def test_he_can_correct_a_customer_who_moved(client, warehouse):
    created = client.post(
        "/api/consignees", json={"name": "Hafrin", "city": "Kottayam"}, headers=warehouse
    ).json()

    res = client.patch(
        f"/api/consignees/{created['id']}",
        json={"city": "Changanassery"},
        headers=warehouse,
    )
    assert res.status_code == 200, res.text


def test_he_can_hand_a_driver_an_advance(client, warehouse):
    """The driver asking for diesel money is standing at his counter."""
    driver = client.post(
        "/api/drivers",
        json={"name": "Shaji", "phone": "9000000302", "create_login": False},
        headers=warehouse,
    ).json()

    res = client.post(
        "/api/advances",
        json={
            "payee_type": "DRIVER",
            "driver_id": driver["id"],
            "advance_date": "2026-10-20",
            "amount": "1000",
            "reason": "Diesel at Thrissur",
        },
        headers=warehouse,
    )
    assert res.status_code == 201, res.text


# ---------------------------------------------------------------------------
# What is not his
# ---------------------------------------------------------------------------


def test_he_cannot_read_the_companys_earnings(client, warehouse):
    assert client.get("/api/reports", headers=warehouse).status_code == 403
    assert client.get("/api/reports/earnings", headers=warehouse).status_code == 403


def test_he_cannot_set_what_a_vendor_is_charged(client, warehouse):
    """He builds freights. He does not price them."""
    assert (
        client.post("/api/vendors", json={"name": "Godrej"}, headers=warehouse).status_code
        == 403
    )
    assert (
        client.post(
            "/api/rate-cards",
            json={
                "vendor_division_id": "00000000-0000-0000-0000-000000000000",
                "base_trip_amount": "1867",
                "effective_from": "2026-10-01",
            },
            headers=warehouse,
        ).status_code
        == 403
    )


def test_he_cannot_reach_the_money_screens(client, warehouse):
    assert client.get("/api/invoices", headers=warehouse).status_code == 403
    assert client.get("/api/money-in", headers=warehouse).status_code == 403
    assert client.get("/api/settlements", headers=warehouse).status_code == 403


def test_he_cannot_make_users_or_roles(client, warehouse):
    assert client.get("/api/roles", headers=warehouse).status_code == 403
    assert client.get("/api/capabilities", headers=warehouse).status_code == 403


# ---------------------------------------------------------------------------
# The rail, which is what he actually sees
# ---------------------------------------------------------------------------


def test_his_rail_offers_what_he_can_open_and_nothing_else(client, warehouse):
    screens = set(client.get("/api/me/access", headers=warehouse).json()["screens"])

    # The day's work, and the lists he keeps.
    assert {"dashboard", "freights", "consignments", "day-sheet", "labels", "returns"} <= screens
    assert {"consignees", "drivers", "vehicles", "labour", "market-vehicles"} <= screens
    assert "advances" in screens

    # Not his.
    assert not screens & {
        "reports",
        "invoices",
        "money-in",
        "settlements",
        "expenses",
        "vendors",
        "rate-cards",
        "unloading-rates",
        "users",
        "roles",
    }


def test_roles_is_a_screen_the_table_knows_about(client, warehouse):
    """It had no entry at all, which is why nothing filtered it out."""
    from app.core.privileges import SCREEN_KEYS

    assert "roles" in SCREEN_KEYS


def test_a_screen_he_cannot_see_is_refused_rather_than_left_hanging(client, warehouse):
    """A 403 is an answer. The spinner that used to follow it was not."""
    res = client.get("/api/roles", headers=warehouse)
    assert res.status_code == 403
    assert res.json()["detail"]


# ---------------------------------------------------------------------------
# The people who should still see the figures
# ---------------------------------------------------------------------------


def test_a_stakeholder_still_reads_the_reports(client, stakeholder):
    """Splitting reports out of office.view must not take them from the
    person whose whole job is reading them."""
    assert client.get("/api/reports", headers=stakeholder).status_code == 200
    assert "reports" in client.get("/api/me/access", headers=stakeholder).json()["screens"]


def test_a_stakeholder_reads_the_invoices_but_moves_nothing(client, stakeholder):
    """Reading what went out is the job. Raising it is not.

    An invoice is read by two people for two reasons — the clerk who raises
    it and the owner who wants to know what the month billed — so reading is
    open to either capability and every write stays behind MONEY.
    """
    assert client.get("/api/invoices", headers=stakeholder).status_code == 200

    assert (
        client.post("/api/consignees", json={"name": "X"}, headers=stakeholder).status_code
        == 403
    )
    assert (
        client.post(
            "/api/invoices",
            json={
                "vendor_division_id": "00000000-0000-0000-0000-000000000000",
                "period_from": "2026-10-01",
                "period_to": "2026-10-31",
            },
            headers=stakeholder,
        ).status_code
        == 403
    )


def test_a_super_admin_still_reaches_everything(client, auth):
    from app.core.privileges import SCREEN_KEYS

    screens = set(client.get("/api/me/access", headers=auth).json()["screens"])
    assert screens == SCREEN_KEYS
