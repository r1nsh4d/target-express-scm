"""Every NOT NULL column added from now on must carry a server_default.

A Python-side `default=` runs when the ORM builds an INSERT. It does nothing
during a migration, so:

    ALTER TABLE driver_pay_terms ADD COLUMN unloading_share_basis VARCHAR(20) NOT NULL

fails on any table that already has rows in it — "column contains null values".
That stopped a live deploy dead, with the application already running against
the new code and failing on every request.

The fix is `server_default=`, which Postgres applies to the existing rows as it
adds the column.

This test is a ratchet, not an audit. The 119 names below predate the rule:
they were created together with their tables, when those tables were empty, so
they never had to survive an ALTER against populated data and changing them now
would be churn for no benefit. Nothing may be ADDED to that list. If this test
fails on a column you just wrote, the column is wrong — not the list.
"""

from app.models import Base


# Columns that existed before this rule. Do not extend.
LEGACY: set[str] = {
    "advances.recovered_amount",
    "advances.status",
    "boxes.status",
    "consignees.geo_confidence",
    "consignees.is_active",
    "consignees.type",
    "consignments.declared_box_count",
    "consignments.status",
    "driver_pay_terms.daily_allowance",
    "driver_pay_terms.incentive_after_points",
    "driver_pay_terms.monthly_salary",
    "driver_pay_terms.per_km_amount",
    "driver_pay_terms.per_point_amount",
    "driver_pay_terms.per_trip_amount",
    "driver_pay_terms.unloading_share_percent",
    "drivers.engagement",
    "drivers.is_active",
    "enquiries.is_spam",
    "enquiries.status",
    "freight_legs.change_reason",
    "freight_legs.sequence",
    "freight_payouts.amount",
    "freight_points.delivered_box_count",
    "freight_points.floor_number",
    "freight_points.has_lift",
    "freight_points.loaded_box_count",
    "freight_points.status",
    "freight_points.unloading_billed",
    "freight_points.unloading_paid",
    "freights.point_count",
    "freights.status",
    "goods_categories.is_active",
    "goods_categories.is_bulky",
    "goods_categories.is_fragile",
    "labour.daily_rate",
    "labour.is_active",
    "labour.per_trip_rate",
    "location_change_requests.status",
    "market_vehicles.is_active",
    "market_vehicles.standing",
    "market_vehicles.times_hired",
    "rate_cards.base_point_charge",
    "rate_cards.detention_pass_through",
    "rate_cards.extra_km_rate",
    "rate_cards.extra_point_rate",
    "rate_cards.included_km",
    "rate_cards.included_points",
    "rate_cards.is_active",
    "rate_cards.toll_pass_through",
    "rate_cards.unloading_basis",
    "rate_cards.unloading_rate",
    "route_preset_points.default_floor_number",
    "route_preset_points.default_has_lift",
    "route_presets.is_active",
    "route_presets.times_used",
    "settlements.advance_recovered",
    "settlements.deductions",
    "settlements.gross_amount",
    "settlements.loading_unloading_amount",
    "settlements.net_payable",
    "settlements.other_amount",
    "settlements.point_incentive_amount",
    "settlements.status",
    "settlements.total_km",
    "settlements.transportation_amount",
    "settlements.trip_count",
    "tracking_sessions.is_active",
    "tracking_sessions.view_count",
    "trip_expenses.approval_status",
    "trip_expenses.billable_to_vendor",
    "trip_expenses.entry_mode",
    "trip_expenses.paid_by",
    "unloading_item_rates.base_rate",
    "unloading_item_rates.charge_floors_with_lift",
    "unloading_item_rates.is_active",
    "unloading_item_rates.max_chargeable_floors",
    "unloading_item_rates.per_floor_rate",
    "users.can_view_earnings",
    "users.is_active",
    "vehicle_hire_terms.includes_unloading",
    "vehicle_hire_terms.minimum_km_per_trip",
    "vehicle_hire_terms.per_point_amount",
    "vehicle_hire_terms.rate_basis",
    "vehicle_hire_terms.rate_value",
    "vehicle_hire_terms.unloading_paid_to_owner",
    "vehicle_owners.is_active",
    "vehicle_types.is_active",
    "vehicles.is_active",
    "vehicles.lr_next_number",
    "vehicles.lr_prefix",
    "vehicles.ownership",
    "vendor_divisions.gst_rate_percent",
    "vendor_divisions.invoice_series",
    "vendor_divisions.is_active",
    "vendor_invoice_lines.base_amount",
    "vendor_invoice_lines.detention",
    "vendor_invoice_lines.extra_km",
    "vendor_invoice_lines.extra_km_amount",
    "vendor_invoice_lines.extra_km_rate",
    "vendor_invoice_lines.extra_point_amount",
    "vendor_invoice_lines.extra_point_rate",
    "vendor_invoice_lines.extra_points",
    "vendor_invoice_lines.included_km",
    "vendor_invoice_lines.included_points",
    "vendor_invoice_lines.km",
    "vendor_invoice_lines.line_total",
    "vendor_invoice_lines.point_count",
    "vendor_invoice_lines.toll",
    "vendor_invoice_lines.unloading",
    "vendor_invoice_lines.unloading_additional",
    "vendor_invoices.cgst",
    "vendor_invoices.igst",
    "vendor_invoices.sgst",
    "vendor_invoices.status",
    "vendor_invoices.taxable_value",
    "vendor_invoices.total",
    "vendor_warehouses.is_active",
    "vendors.is_active",
    "vendors.payment_terms_days"
}


def test_a_new_not_null_column_declares_a_server_default():
    offenders = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if column.primary_key or column.nullable:
                continue
            if column.server_default is not None or column.default is None:
                continue
            name = f"{table.name}.{column.name}"
            if name not in LEGACY:
                offenders.append(name)

    assert not offenders, (
        "These NOT NULL columns have a Python default but no server_default, so "
        "the migration that adds them will fail against a table that already "
        "has rows. Add server_default= alongside default=.\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_the_columns_that_broke_the_deploy_are_fixed():
    """The four that actually failed, pinned by name so a refactor cannot
    quietly drop the server_default again."""
    for table_name, column_name in (
        ("driver_pay_terms", "unloading_share_basis"),
        ("freight_points", "coolie_paid"),
        ("freight_points", "coolie_billed"),
        ("vendor_invoice_lines", "coolie"),
    ):
        column = Base.metadata.tables[table_name].c[column_name]
        assert column.server_default is not None, f"{table_name}.{column_name}"


def test_the_legacy_list_has_not_grown():
    """A ratchet only works if it cannot be loosened by adding a name."""
    assert len(LEGACY) == 119
