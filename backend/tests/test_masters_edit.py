"""Editing and retiring master records.

Every master was create-only until now. A driver's name typed wrong stayed wrong
forever; a customer who moved could not be corrected. That is how a list stops
being trusted and people go back to the spreadsheet.

Three rules these tests hold:

  * A PATCH changes only what it sends. Omitting a field must leave it alone,
    not blank it — otherwise every partial edit silently wipes whatever the form
    did not happen to include.
  * DELETE retires, it does not destroy. Everything here is referenced by a
    freight, a point or a settlement, and those have to keep answering.
  * A rate card cannot be edited at all. That is the feature, not a gap.
"""

import pytest

pytestmark = pytest.mark.tables(
    "users",
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
    "freights",
    "freight_points",
    "consignments",
    "freight_legs",
)


@pytest.fixture()
def customer(client, auth) -> str:
    res = client.post(
        "/api/consignees",
        json={
            "name": "Anand Agencies",
            "type": "RETAIL_CUSTOMER",
            "phone": "9847012345",
            "city": "Kasaragod",
            "address": "Main Road",
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ---------------------------------------------------------------------------
# Partial updates
# ---------------------------------------------------------------------------


def test_a_name_can_be_corrected(client, auth, customer):
    res = client.patch(
        f"/api/consignees/{customer}", json={"name": "Anand Agencies & Sons"}, headers=auth
    )
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Anand Agencies & Sons"


def test_a_patch_leaves_untouched_fields_alone(client, auth, customer):
    """The rule that stops every edit being a data loss event."""
    client.patch(f"/api/consignees/{customer}", json={"name": "Renamed"}, headers=auth)

    rows = client.get("/api/consignees", headers=auth).json()
    row = next(r for r in rows if r["id"] == customer)

    assert row["name"] == "Renamed"
    assert row["phone"] == "9847012345"      # not sent, not wiped
    assert row["city"] == "Kasaragod"
    assert row["address"] == "Main Road"


def test_a_field_can_be_deliberately_cleared(client, auth, customer):
    """Sending null is different from not sending at all."""
    client.patch(f"/api/consignees/{customer}", json={"landmark": None}, headers=auth)
    rows = client.get("/api/consignees", headers=auth).json()
    assert next(r for r in rows if r["id"] == customer)["landmark"] is None


def test_editing_something_that_does_not_exist_is_a_404(client, auth):
    res = client.patch(
        "/api/consignees/00000000-0000-0000-0000-000000000000",
        json={"name": "Nobody"},
        headers=auth,
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Retiring
# ---------------------------------------------------------------------------


def test_delete_retires_rather_than_destroys(client, auth, customer):
    """The record has to keep answering for the deliveries it is part of."""
    assert client.delete(f"/api/consignees/{customer}", headers=auth).status_code == 204

    rows = client.get("/api/consignees?include_inactive=true", headers=auth).json()
    row = next((r for r in rows if r["id"] == customer), None)
    assert row is not None, "the record was destroyed, not retired"
    assert row["is_active"] is False


def test_a_retired_customer_drops_out_of_the_normal_list(client, auth, customer):
    client.delete(f"/api/consignees/{customer}", headers=auth)
    rows = client.get("/api/consignees", headers=auth).json()
    assert all(r["id"] != customer for r in rows)


def test_a_retired_customer_can_be_brought_back(client, auth, customer):
    client.delete(f"/api/consignees/{customer}", headers=auth)
    res = client.post(f"/api/consignees/{customer}/restore", headers=auth)
    assert res.status_code == 200
    assert res.json()["is_active"] is True

    rows = client.get("/api/consignees", headers=auth).json()
    assert any(r["id"] == customer for r in rows)


def test_usage_says_why_a_record_is_held(client, auth, customer):
    """'Can I delete this customer' should get a count, not a shrug."""
    res = client.get(f"/api/consignees/{customer}/usage", headers=auth)
    assert res.status_code == 200, res.text

    body = res.json()
    assert body["in_use"] is False
    assert "Not used" in body["summary"]


# ---------------------------------------------------------------------------
# Drivers: the login moves with them
# ---------------------------------------------------------------------------


@pytest.fixture()
def driver(client, auth) -> str:
    res = client.post(
        "/api/drivers",
        json={
            "name": "Rajesh K",
            "phone": "9000000010",
            "engagement": "OWN_STAFF",
            "create_login": True,
            "password": "target123",
        },
        headers=auth,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_correcting_a_driver_phone_also_moves_his_login(client, auth, driver):
    """The phone number IS the username. Fixing one and not the other locks him
    out with nobody realising why."""
    client.patch(f"/api/drivers/{driver}", json={"phone": "9000000055"}, headers=auth)

    users = client.get("/api/auth/users", headers=auth).json()
    assert any(u["phone"] == "9000000055" for u in users)
    assert not any(u["phone"] == "9000000010" for u in users)


def test_a_phone_already_in_use_is_refused_clearly(client, auth, driver):
    """Not a 500 from the database. The admin is told whose number it is."""
    res = client.patch(
        f"/api/drivers/{driver}",
        json={"phone": "9000000099"},   # the test admin's own login
        headers=auth,
    )
    assert res.status_code == 409, res.text
    assert "already the login" in res.json()["detail"]


def test_retiring_a_driver_disables_his_login(client, auth, driver):
    """Which is what someone actually means when they say a driver has left."""
    client.delete(f"/api/drivers/{driver}", headers=auth)

    users = client.get("/api/auth/users", headers=auth).json()
    his = next((u for u in users if u["full_name"] == "Rajesh K"), None)
    assert his is not None
    assert his["is_active"] is False


# ---------------------------------------------------------------------------
# Rate cards stay immutable
# ---------------------------------------------------------------------------


def test_a_rate_card_cannot_be_edited(client):
    """A rate agreed in April must still price an April freight in December.
    Editing a card would reprice work already invoiced against it."""
    from app.main import app

    paths = app.openapi()["paths"]
    assert "patch" not in paths.get("/api/rate-cards/{item_id}", {})


def test_a_rate_card_can_be_retired(client):
    """Retiring stops it applying to future freights without touching anything
    it has already priced."""
    from app.main import app

    paths = app.openapi()["paths"]
    assert "delete" in paths.get("/api/rate-cards/{item_id}", {})


def test_a_vehicle_odometer_cannot_be_typed_in(client):
    """The closing reading is a chain across every freight the lorry has run,
    and it is a fraud control. Corrections go through the freight, where they
    are logged with a reason."""
    from app.api.routes.masters_edit import VehiclePatch

    assert "last_closing_km" not in VehiclePatch.model_fields
    assert "lr_next_number" not in VehiclePatch.model_fields
