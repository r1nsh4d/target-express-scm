"""Fill the application with believable data, for showing a client.

    python -m app.demo

`app.seed` already creates the masters and a handful of freights taken from
Target Express's own invoices — real trip numbers, real LR numbers, real
odometer readings. What it does not create is everything that hangs off a
freight, so most of the application opens on "no data yet": no bills, so no
boxes, so nothing to print at Sorting & labels; no invoice; no settlement; no
saved routes; an empty market vehicle phonebook; an empty enquiry list.

A demo where two screens work and nine are blank is worse than no demo.

This fills in the rest. It runs AFTER the seed and is safe to run twice — every
step checks for its own work first, so a half-finished run can simply be
repeated.

Everything here is produced through the real services wherever one exists.
Invoices are priced by `invoicing.create_invoice`, payouts by
`completion.record_leg_payouts`. That is deliberate: data built by hand would
look right while reconciling to nothing, and the first thing a client does with
an invoice is add up the column.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.consignee import Consignee
from app.models.consignment import Box, Consignment
from app.models.enquiry import Enquiry
from app.models.enums import (
    BoxStatus,
    ConsignmentStatus,
    EnquiryStatus,
    EntryMode,
    ExpenseType,
    FreightPointStatus,
    FreightStatus,
    MarketVehicleStanding,
    PaidBy,
)
from app.models.expense import TripExpense
from app.models.fleet import VehicleType
from app.models.freight import Freight, FreightPoint
from app.models.market_vehicle import MarketVehicle
from app.models.route_preset import RoutePreset, RoutePresetPoint
from app.models.user import User
from app.models.vendor import VendorDivision, VendorWarehouse
from app.services import completion, invoicing

# Fixed seed: the demo looks the same every time it is shown. A client being
# walked through the same screen twice should not see different numbers.
RNG = random.Random(20260207)

# Articles a spare-parts run actually carries, so the labels and the box list
# read like the real thing rather than "Item 1, Item 2".
ARTICLES = [
    "Compressor assembly",
    "Door gasket",
    "Evaporator coil",
    "Thermostat unit",
    "Condenser fan",
    "Shelf set",
    "Control panel",
    "Drain tray",
    "Hinge kit",
    "Wiring harness",
]


def _say(message: str) -> None:
    print(f"  {message}")


# ---------------------------------------------------------------------------
# Bills and boxes — without these nothing can be labelled or scanned
# ---------------------------------------------------------------------------


def add_consignments(db: Session) -> int:
    """One or two vendor bills on each delivery point, and the cartons under them.

    This is the step that makes Sorting & labels work: a label is printed per
    box, and boxes only exist under a bill.
    """
    if db.execute(select(Consignment).limit(1)).scalar_one_or_none() is not None:
        _say("bills already present")
        return 0

    freights = db.execute(select(Freight).order_by(Freight.trip_date)).scalars().all()
    created = 0
    bill_seq = 8800

    for freight in freights:
        for point in sorted(freight.points, key=lambda p: p.sequence):
            # One bill usually, two sometimes — a point carrying two customers'
            # goods is normal and is why the bill number is on every sticker.
            for _ in range(RNG.choice([1, 1, 1, 2])):
                bill_seq += 1
                box_count = RNG.randint(2, 6)

                consignment = Consignment(
                    vendor_division_id=freight.vendor_division_id,
                    warehouse_id=freight.warehouse_id,
                    consignee_id=point.consignee_id,
                    freight_point_id=point.id,
                    vendor_bill_no=f"GDJ/{bill_seq}",
                    bill_date=freight.trip_date - timedelta(days=1),
                    declared_box_count=box_count,
                    status=ConsignmentStatus.RECEIVED,
                )
                db.add(consignment)
                db.flush()

                delivered = point.status in (
                    FreightPointStatus.DELIVERED,
                    FreightPointStatus.PART_DELIVERED,
                )
                for n in range(1, box_count + 1):
                    db.add(
                        Box(
                            consignment_id=consignment.id,
                            item_no=n,
                            # Same shape the application issues: TE-<token>-<nnn>
                            barcode=f"TE-{consignment.vendor_bill_no[-4:]}{point.sequence}-{n:03d}",
                            item_name=RNG.choice(ARTICLES),
                            status=BoxStatus.DELIVERED if delivered else BoxStatus.LOADED,
                            scanned_at=(
                                datetime.combine(freight.trip_date, datetime.min.time())
                                + timedelta(hours=10 + point.sequence)
                                if delivered
                                else None
                            ),
                        )
                    )
                created += 1

            # Keep the point's counts honest against the boxes just created.
            boxes_here = sum(
                len(c.boxes) for c in point.consignments if c.boxes is not None
            )
            point.loaded_box_count = boxes_here
            if point.status in (
                FreightPointStatus.DELIVERED,
                FreightPointStatus.PART_DELIVERED,
            ):
                point.delivered_box_count = boxes_here

    db.commit()
    _say(f"{created} vendor bills, with their cartons")
    return created


def add_furniture_freight(db: Session, admin: User) -> None:
    """One completed run on the furniture division.

    Every freight the seed creates is on Godrej Appliance Spare, and spare parts
    bill NOTHING for unloading — so a demo built only on those shows an empty
    unloading column on the invoice, which is the opposite of the point. Target
    Express's unloading pricing is per article plus a charge for every floor
    climbed, and that is the thing worth showing.

    So: one furniture run, to third and second floors, carrying articles that
    are actually on the rate sheet.
    """
    from app.models.fleet import Driver, Vehicle
    from app.models.freight import FreightLeg
    from app.models.rating import UnloadingItemRate

    trip_no = "Y26006021"
    if db.execute(select(Freight).where(Freight.trip_no == trip_no)).scalar_one_or_none():
        _say("furniture run already present")
        return

    division = db.execute(
        select(VendorDivision).where(VendorDivision.code == "GODREJ-OCP")
    ).scalar_one_or_none()
    warehouse = db.execute(select(VendorWarehouse)).scalars().first()
    vehicle = db.execute(select(Vehicle)).scalars().first()
    driver = db.execute(select(Driver)).scalars().first()
    customers = db.execute(select(Consignee).order_by(Consignee.name)).scalars().all()

    if not all((division, warehouse, vehicle, driver)) or len(customers) < 3:
        _say("cannot build the furniture run — masters missing")
        return

    # Articles priced on the furniture sheet, with the floor each goes to.
    # A wardrobe to the third floor with no lift is the case the whole per-floor
    # charge exists for.
    drops = [
        (customers[0], 0, False, [("WARDROBE", "Wardrobe", 1), ("CHAIR", "Chair", 4)]),
        (customers[1], 3, False, [("BED", "Bed", 1), ("MATTRESS", "Mattress", 2)]),
        (customers[2], 2, True, [("SOFA", "Sofa", 1), ("TABLE", "Table", 2)]),
    ]

    trip_date = date.today() - timedelta(days=3)
    start_km, end_km = 190275, 190648

    freight = Freight(
        trip_no=trip_no,
        lr_no="804",
        trip_date=trip_date,
        vendor_division_id=division.id,
        warehouse_id=warehouse.id,
        status=FreightStatus.COMPLETED,
        destination_text=", ".join(c.city or c.name for c in [d[0] for d in drops]),
        point_count=len(drops),
        total_km=end_km - start_km,
        dispatched_at=datetime.combine(trip_date, datetime.min.time()),
        returned_at=datetime.combine(trip_date, datetime.max.time()),
        completed_at=datetime.combine(trip_date, datetime.max.time()),
        created_by_id=admin.id,
        remarks="Furniture run — unloading billed per article plus the climb.",
    )
    db.add(freight)
    db.flush()

    db.add(
        FreightLeg(
            freight_id=freight.id,
            sequence=1,
            vehicle_id=vehicle.id,
            driver_id=driver.id,
            start_odometer=start_km,
            end_odometer=end_km,
            leg_distance_km=end_km - start_km,
            started_at=freight.dispatched_at,
            ended_at=freight.returned_at,
        )
    )

    rates = {
        r.item_code: r
        for r in db.execute(
            select(UnloadingItemRate).where(
                UnloadingItemRate.vendor_division_id == division.id
            )
        ).scalars().all()
    }

    bill_seq = 9100
    for i, (customer, floor, lift, articles) in enumerate(drops, start=1):
        point = FreightPoint(
            freight_id=freight.id,
            sequence=i,
            consignee_id=customer.id,
            address_snapshot=customer.address,
            floor_number=floor,
            has_lift=lift,
            status=FreightPointStatus.DELIVERED,
            receiver_name="Received at the door",
            arrived_at=freight.dispatched_at + timedelta(hours=2 * i),
            departed_at=freight.dispatched_at + timedelta(hours=2 * i, minutes=40),
        )
        db.add(point)
        db.flush()

        bill_seq += 1
        total_boxes = sum(qty for _, _, qty in articles)
        consignment = Consignment(
            vendor_division_id=division.id,
            warehouse_id=warehouse.id,
            consignee_id=customer.id,
            freight_point_id=point.id,
            vendor_bill_no=f"OCP/{bill_seq}",
            bill_date=trip_date - timedelta(days=1),
            declared_box_count=total_boxes,
            status=ConsignmentStatus.RECEIVED,
        )
        db.add(consignment)
        db.flush()

        # What the unloading actually comes to, by the sheet: base per article,
        # plus the per-floor rate for each floor climbed. A lift cancels the
        # climb unless the article's own rate says otherwise.
        due = Decimal("0")
        item_no = 0
        for code, name, qty in articles:
            rate = rates.get(code)
            for _ in range(qty):
                item_no += 1
                db.add(
                    Box(
                        consignment_id=consignment.id,
                        item_no=item_no,
                        barcode=f"TE-OCP{bill_seq}{i}-{item_no:03d}",
                        item_code=code,
                        item_name=name,
                        status=BoxStatus.DELIVERED,
                        scanned_at=point.departed_at,
                    )
                )
                if rate is not None:
                    climb = 0 if (lift and not rate.charge_floors_with_lift) else floor
                    if rate.max_chargeable_floors:
                        climb = min(climb, rate.max_chargeable_floors)
                    due += Decimal(rate.base_rate) + Decimal(climb) * Decimal(
                        rate.per_floor_rate
                    )

        point.loaded_box_count = total_boxes
        point.delivered_box_count = total_boxes
        point.unloading_paid = due
        point.unloading_billed = due

    db.commit()
    _say(f"furniture run {trip_no}: {len(drops)} points, unloading priced per article")


# ---------------------------------------------------------------------------
# What happened on the road
# ---------------------------------------------------------------------------


def add_point_charges(db: Session) -> None:
    """Unloading on every delivered point, and coolie on one of them.

    The coolie row matters for the demo: it is the charge Target Express cannot
    currently evidence on paper, and seeing it priced apart from unloading on an
    invoice is the clearest version of the argument.
    """
    points = (
        db.execute(
            select(FreightPoint).where(
                FreightPoint.status.in_(
                    [FreightPointStatus.DELIVERED, FreightPointStatus.PART_DELIVERED]
                )
            )
        )
        .scalars()
        .all()
    )
    if not points:
        _say("no delivered points to charge")
        return

    # Points whose unloading was already priced off the furniture article sheet
    # are left alone. Overwriting them with a round number would throw away the
    # one place the per-article, per-floor pricing is visible.
    untouched = [p for p in points if not Decimal(p.unloading_paid or 0)]
    if not untouched:
        _say("point charges already present")
        return

    for point in untouched:
        paid = Decimal(RNG.choice([120, 150, 180, 200, 240]))
        point.unloading_paid = paid
        point.unloading_billed = paid

    # One stop where a local porter gang took cash before letting the lorry be
    # unloaded. Reimbursed in full, billed to the vendor, and reasoned.
    marked = (untouched or points)[len(untouched or points) // 2]
    marked.coolie_paid = Decimal("450")
    marked.coolie_billed = Decimal("450")
    marked.coolie_note = (
        "Porter gang at the market gate; would not let us unload until paid. "
        "Spoke to the vendor's supervisor on the phone before handing it over."
    )

    db.commit()
    _say(f"unloading on {len(untouched)} points, coolie on 1 ({marked.consignee.name})")


def add_expenses(db: Session, admin: User) -> None:
    """Toll and diesel against completed freights, some still awaiting approval."""
    if db.execute(select(TripExpense).limit(1)).scalar_one_or_none() is not None:
        _say("expenses already present")
        return

    freights = (
        db.execute(select(Freight).where(Freight.status == FreightStatus.COMPLETED))
        .scalars()
        .all()
    )
    count = 0
    for freight in freights[:4]:
        db.add(
            TripExpense(
                freight_id=freight.id,
                type=ExpenseType.TOLL,
                amount=Decimal(RNG.choice([180, 240, 290, 310])),
                paid_by=PaidBy.DRIVER,
                billable_to_vendor=True,
                entered_by_id=admin.id,
                entry_mode=EntryMode.SELF,
                remarks="Receipt photographed at the plaza",
            )
        )
        count += 1

    db.commit()
    _say(f"{count} tolls, billable to the vendor")


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def add_payouts(db: Session) -> None:
    """What each completed leg pays its driver or the vehicle's owner."""
    freights = (
        db.execute(select(Freight).where(Freight.status == FreightStatus.COMPLETED))
        .scalars()
        .all()
    )
    written = 0
    for freight in freights:
        for leg in freight.legs:
            if leg.end_odometer is None:
                continue
            try:
                written += len(completion.record_leg_payouts(db, leg))
            except Exception as exc:  # pragma: no cover - demo data only
                _say(f"payout skipped for {freight.trip_no}: {exc}")
    db.commit()
    _say(f"{written} payout rows across the completed legs")


def add_invoice(db: Session, admin: User) -> None:
    """Issue one real invoice over the completed freights.

    Through `create_invoice`, not by hand: the first thing anyone does with an
    invoice is add up the column, and a hand-built one would not survive that.
    """
    from app.models.billing import VendorInvoice

    if db.execute(select(VendorInvoice).limit(1)).scalar_one_or_none() is not None:
        _say("invoice already present")
        return

    # Every division with completed work, not just the first one found. Spare
    # parts and furniture bill differently — furniture is where the unloading
    # column has anything in it — so invoicing only one of them shows half the
    # billing story.
    divisions = db.execute(select(VendorDivision)).scalars().all()
    today = date.today()
    raised = 0

    for division in divisions:
        try:
            invoice = invoicing.create_invoice(
                db,
                division=division,
                period_from=today - timedelta(days=45),
                period_to=today,
                invoice_date=today,
                issued_by_id=admin.id,
            )
            db.commit()
            raised += 1
            _say(
                f"invoice {invoice.invoice_no} ({division.name}): "
                f"{len(invoice.lines)} lines, total {invoice.total}"
            )
        except ValueError as exc:
            db.rollback()
            _say(f"{division.name}: no invoice ({exc})")

    if not raised:
        _say("no invoices raised")


# ---------------------------------------------------------------------------
# Planning tools
# ---------------------------------------------------------------------------


def add_route_presets(db: Session) -> None:
    """The office's own numbered rounds."""
    if db.execute(select(RoutePreset).limit(1)).scalar_one_or_none() is not None:
        _say("saved routes already present")
        return

    division = db.execute(select(VendorDivision)).scalars().first()
    warehouse = db.execute(select(VendorWarehouse)).scalars().first()
    customers = db.execute(select(Consignee).order_by(Consignee.name)).scalars().all()
    if len(customers) < 3:
        _say("not enough customers for a saved route")
        return

    rounds = [
        ("No. 11", customers[:4], 640, "Runs Tuesdays. Kasaragod first, gate shuts at 1pm."),
        ("No. 7 — Malabar", customers[1:5], 420, "Two drops before noon, rest after lunch."),
        ("South loop", customers[-3:], 900, "Long day. Leaves at 5am."),
    ]

    for name, stops, km, note in rounds:
        preset = RoutePreset(
            name=name,
            vendor_division_id=division.id if division else None,
            warehouse_id=warehouse.id if warehouse else None,
            typical_round_trip_km=km,
            notes=note,
            times_used=RNG.randint(3, 22),
        )
        db.add(preset)
        db.flush()
        for i, customer in enumerate(stops, start=1):
            db.add(
                RoutePresetPoint(
                    preset_id=preset.id,
                    consignee_id=customer.id,
                    sequence=i,
                    default_floor_number=RNG.choice([0, 0, 0, 1, 2]),
                    default_has_lift=RNG.choice([False, False, True]),
                )
            )

    db.commit()
    _say(f"{len(rounds)} saved routes")


def add_market_vehicles(db: Session) -> None:
    """The phonebook of lorries that can be hired in."""
    if db.execute(select(MarketVehicle).limit(1)).scalar_one_or_none() is not None:
        _say("market vehicles already present")
        return

    dost = db.execute(select(VehicleType).where(VehicleType.name == "DOST")).scalars().first()
    today = date.today()

    rows = [
        ("Shaji Transports", "9847011221", "KL13AB4455", "Kozhikode",
         "Two DOSTs at a day's notice", 4200, 12, MarketVehicleStanding.RELIABLE),
        ("Noushad (broker)", "9847033440", None, "Kochi",
         "Whatever is free; usually a 407", 5600, 31, MarketVehicleStanding.RELIABLE),
        ("Jaleel Lorry Service", "9847055667", "KL58CD7788", "Kannur",
         "One 709, long runs only", 7800, 64, MarketVehicleStanding.UNTRIED),
        ("Rafeeq", "9847077889", "KL14EF1122", "Thrissur",
         "Did not turn up twice in November", 4000, 120, MarketVehicleStanding.AVOID),
    ]

    for name, phone, reg, city, note, rate, days_ago, standing in rows:
        db.add(
            MarketVehicle(
                contact_name=name,
                phone=phone,
                registration_no=reg,
                vehicle_type_id=dost.id if dost else None,
                capacity_note=note,
                base_city=city,
                last_hired_rate=Decimal(rate),
                last_hired_on=today - timedelta(days=days_ago),
                times_hired=RNG.randint(1, 9),
                standing=standing,
            )
        )

    db.commit()
    _say(f"{len(rows)} market vehicles")


def add_enquiries(db: Session) -> None:
    """Businesses who filled in the form on the website."""
    if db.execute(select(Enquiry).limit(1)).scalar_one_or_none() is not None:
        _say("enquiries already present")
        return

    rows = [
        ("Anand Agencies", "Rahul Menon", "9847012345", "rahul@anandagencies.in",
         "Furniture", "Kochi", "about 400 boxes",
         "We move furniture to dealers across north Kerala. Looking for a rate card.",
         EnquiryStatus.NEW, 0),
        ("Beena Home Appliances", "Beena K", "9847023456", None,
         "Appliance spares", "Kozhikode", "around 15 runs",
         "Our current transporter cannot give us delivery proof.",
         EnquiryStatus.CONTACTED, 2),
        ("Thrissur Traders", "Vinod P", "9847034567", "vinod@tcrtraders.com",
         "Mixed", "Thrissur", "not sure yet", None, EnquiryStatus.QUOTED, 6),
    ]

    for company, person, phone, email, goods, city, volume, message, status, days_ago in rows:
        db.add(
            Enquiry(
                company_name=company,
                contact_name=person,
                phone=phone,
                email=email,
                goods_type=goods,
                origin_city=city,
                monthly_volume=volume,
                message=message,
                status=status,
                contacted_at=(
                    datetime.now() - timedelta(days=days_ago)
                    if status != EnquiryStatus.NEW
                    else None
                ),
                created_at=datetime.now() - timedelta(days=days_ago, hours=3),
            )
        )

    db.commit()
    _say(f"{len(rows)} enquiries (1 still waiting for a call)")


# ---------------------------------------------------------------------------


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.execute(select(User).order_by(User.created_at)).scalars().first()
        if admin is None:
            raise SystemExit(
                "No users found. Run `python -m app.seed` first — this fills in "
                "what hangs off the freights it creates."
            )

        if db.execute(select(Freight).limit(1)).scalar_one_or_none() is None:
            raise SystemExit(
                "No freights found. Run `python -m app.seed` first."
            )

        print("\nFilling in the demo data\n")
        add_consignments(db)
        add_furniture_freight(db, admin)
        add_point_charges(db)
        add_expenses(db, admin)
        add_payouts(db)
        add_invoice(db, admin)
        add_route_presets(db)
        add_market_vehicles(db)
        add_enquiries(db)

        print("\nDone. Worth showing, in this order:\n")
        print("  Dashboard         today's runs, and an enquiry nobody has called")
        print("  Freights          open one, look at its points and bills")
        print("  Sorting & labels  pick a freight, press Print — QR on every sticker")
        print("  Saved routes      'No. 11' — then New trip, and pick it")
        print("  Vendor invoices   open it; unloading and coolie are separate columns")
        print("  Settlements       what each driver is owed, head by head")
        print("  Market vehicles   who to call, and what we paid them last")
        print("  Enquiries         the website form, with one waiting\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
