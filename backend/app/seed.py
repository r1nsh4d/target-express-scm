"""Seed the database with the real Godrej setup and a few worked trips.

Everything here is taken from Target Express invoices 191/2026-27/022 and /023:
the two vendor divisions, the vehicle registrations, the rate terms, and the
odometer readings. Two known anomalies are reproduced deliberately so the
dashboard's odometer control has something to catch on first run:

  - KL41U0317 closes at 189143 and reopens at 189375 (a 232 km cross-division gap)
  - KL07DE1129 closes at 133432 and reopens at 133422 (ten kilometres backwards)

Run with:  python -m app.seed
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.consignee import Consignee
from app.models.enums import (
    ConsigneeType,
    DriverEngagement,
    FreightPointStatus,
    FreightStatus,
    GeoConfidence,
    HireRateBasis,
    LegChangeReason,
    UnloadingBasis,
    UserRole,
    VehicleOwnership,
)
from app.models.fleet import (
    Driver,
    DriverPayTerms,
    Labour,
    Vehicle,
    VehicleHireTerms,
    VehicleOwner,
    VehicleType,
)
from app.models.freight import Freight, FreightLeg, FreightPoint
from app.models.rating import RateCard, UnloadingItemRate
from app.models.user import User
from app.models.vendor import GoodsCategory, Vendor, VendorDivision, VendorWarehouse

CONTRACT_START = date(2026, 4, 1)


def _get_or_create(db: Session, model, defaults: dict | None = None, **lookup):
    instance = db.execute(select(model).filter_by(**lookup)).scalar_one_or_none()
    if instance is not None:
        return instance, False
    instance = model(**lookup, **(defaults or {}))
    db.add(instance)
    db.flush()
    return instance, True


def seed_users(db: Session) -> dict[str, User]:
    # can_view_earnings is off for drivers on rented vehicles: they run the trip
    # but Target Express does not pay them, so there is nothing for them to see.
    people = [
        ("Super Admin", "9000000001", UserRole.SUPER_ADMIN, True),
        ("Operations Desk", "9000000002", UserRole.OPS_ADMIN, True),
        ("Godrej Warehouse Admin", "9000000003", UserRole.WAREHOUSE_ADMIN, False),
        ("Accounts", "9000000004", UserRole.ACCOUNTS, True),
        ("Management", "9000000005", UserRole.STAKEHOLDER, True),
        ("Rajesh K", "9000000010", UserRole.DRIVER, True),
        ("Suresh M", "9000000011", UserRole.DRIVER, True),
        ("Anil P", "9000000012", UserRole.DRIVER, True),
        # Drives the rented lorry for its owner.
        ("Basheer C", "9000000013", UserRole.DRIVER, False),
    ]
    created: dict[str, User] = {}
    for name, phone, role, can_view_earnings in people:
        user, _ = _get_or_create(
            db,
            User,
            {
                "full_name": name,
                "role": role,
                "can_view_earnings": can_view_earnings,
                "hashed_password": hash_password("target123"),
            },
            phone=phone,
        )
        created[phone] = user
    return created


def seed_masters(db: Session) -> dict:
    spares, _ = _get_or_create(
        db, GoodsCategory, {"name": "Spare Parts", "is_bulky": False}, code="SPARES"
    )
    furniture, _ = _get_or_create(
        db, GoodsCategory, {"name": "Furniture", "is_bulky": True}, code="FURNITURE"
    )

    godrej, _ = _get_or_create(
        db,
        Vendor,
        {"gstin": "32AAACG0000A1Z5", "contact_person": "Godrej Logistics Desk"},
        name="Godrej",
    )

    appliance_spare, _ = _get_or_create(
        db,
        VendorDivision,
        {
            "vendor_id": godrej.id,
            "name": "Godrej Appliance Spare",
            "goods_category_id": spares.id,
            "invoice_series": "191",
            "gst_rate_percent": Decimal("12"),
        },
        code="GODREJ-APPLIANCE-SPARE",
    )
    ocp, _ = _get_or_create(
        db,
        VendorDivision,
        {
            "vendor_id": godrej.id,
            "name": "Godrej OCP",
            "goods_category_id": furniture.id,
            "invoice_series": "191",
            "gst_rate_percent": Decimal("12"),
        },
        code="GODREJ-OCP",
    )

    warehouse, _ = _get_or_create(
        db,
        VendorWarehouse,
        {
            "vendor_id": godrej.id,
            "name": "Godrej Warehouse, Ernakulam",
            "latitude": Decimal("10.0159"),
            "longitude": Decimal("76.3419"),
        },
        code="GODREJ-EKM",
    )

    # Terms recovered from both invoices. Spare parts bill no unloading;
    # furniture does, and its basis is still to be confirmed with the client.
    # Spare parts bill no unloading at all; furniture bills per article plus a
    # climb charge per floor.
    for division, unloading_basis in ((appliance_spare, UnloadingBasis.NOT_APPLICABLE),
                                      (ocp, UnloadingBasis.PER_ITEM_FLOOR)):
        _get_or_create(
            db,
            RateCard,
            {
                "base_trip_amount": Decimal("1867.00"),
                "included_km": 60,
                "extra_km_rate": Decimal("17.00"),
                "included_points": 3,
                "extra_point_rate": Decimal("175.00"),
                "unloading_basis": unloading_basis,
                "notes": "Recovered from invoices 191/2026-27/022 and /023.",
            },
            vendor_division_id=division.id,
            vehicle_type_id=None,
            effective_from=CONTRACT_START,
        )

    # Furniture unloading is priced per article plus a climb charge per floor.
    # The chair line is the client's own worked example: 50 on the ground, 10 a
    # floor, so 90 to the 4th floor.
    furniture_rates = [
        ("CHAIR", "Chair", "50", "10"),
        ("TABLE", "Table", "120", "25"),
        ("WARDROBE", "Wardrobe", "400", "80"),
        ("BED", "Bed", "350", "70"),
        ("MATTRESS", "Mattress", "150", "30"),
        ("SOFA", "Sofa", "300", "60"),
    ]
    for code, name, base, per_floor in furniture_rates:
        _get_or_create(
            db,
            UnloadingItemRate,
            {
                "item_name": name,
                "base_rate": Decimal(base),
                "per_floor_rate": Decimal(per_floor),
                "charge_floors_with_lift": False,
            },
            vendor_division_id=ocp.id,
            item_code=code,
            effective_from=CONTRACT_START,
        )

    # Loading crew at the godown. Largely the same faces every day, so the admin
    # picks a name rather than retyping it.
    for labour_name, labour_phone in [
        ("Shaji", "9846200001"),
        ("Muneer", "9846200002"),
        ("Vinod", "9846200003"),
    ]:
        _get_or_create(
            db,
            Labour,
            {
                "phone": labour_phone,
                "warehouse_id": warehouse.id,
                "per_trip_rate": Decimal("300.00"),
            },
            name=labour_name,
        )

    dost, _ = _get_or_create(db, VehicleType, {"capacity_kg": 1250}, name="DOST")
    _get_or_create(db, VehicleType, {"capacity_kg": 5000}, name="509F")

    # Registrations and opening readings as they appear on the July invoice.
    vehicle_rows = [
        ("KL07CW3317", 238165, "774"),
        ("KL41U0317", 188250, "775"),
        ("KL07DE1175", 140041, "776"),
        ("KL75E2101", 66099, "851"),
        ("KL4156965", 249946, "778"),
        ("KL12N5176", 148427, "780"),
        ("KL07DE1129", 132933, "783"),
    ]
    vehicles: dict[str, Vehicle] = {}
    for reg, opening_km, lr_start in vehicle_rows:
        vehicle, _ = _get_or_create(
            db,
            Vehicle,
            {
                "vehicle_type_id": dost.id,
                "ownership": VehicleOwnership.OWNED,
                "last_closing_km": opening_km,
                "lr_next_number": int(lr_start),
            },
            registration_no=reg,
        )
        vehicles[reg] = vehicle

    # One rented vehicle, so the payee rule has something to demonstrate: this
    # trip's money settles to the owner, not to the driver at the wheel.
    owner, _ = _get_or_create(
        db,
        VehicleOwner,
        {
            "name": "Ibrahim Haji",
            "pan": "ABCPI1234K",
            "bank_name": "Federal Bank",
            "address": "Perinthalmanna, Malappuram",
        },
        phone="9447700001",
    )
    rented, created = _get_or_create(
        db,
        Vehicle,
        {
            "vehicle_type_id": dost.id,
            "ownership": VehicleOwnership.HIRED,
            "owner_id": owner.id,
            "last_closing_km": 88_400,
            "lr_next_number": 901,
        },
        registration_no="KL10AL4477",
    )
    if created:
        db.add(
            VehicleHireTerms(
                vehicle_id=rented.id,
                rate_basis=HireRateBasis.PER_KM,
                rate_value=Decimal("13.00"),
                minimum_km_per_trip=150,
                includes_unloading=False,
                effective_from=CONTRACT_START,
            )
        )
    vehicles["KL10AL4477"] = rented

    return {
        "divisions": {"spare": appliance_spare, "ocp": ocp},
        "warehouse": warehouse,
        "vehicles": vehicles,
    }


def seed_drivers(db: Session, users: dict[str, User], vehicles: dict[str, Vehicle]) -> list[Driver]:
    rows = [
        ("Rajesh K", "9000000010", "KL07CW3317"),
        ("Suresh M", "9000000011", "KL41U0317"),
        ("Anil P", "9000000012", "KL07DE1129"),
        ("Basheer C", "9000000013", "KL10AL4477"),
    ]
    drivers = []
    for name, phone, reg in rows:
        vehicle = vehicles[reg]
        on_rental = vehicle.ownership == VehicleOwnership.HIRED

        driver, created = _get_or_create(
            db,
            Driver,
            {
                "name": name,
                "user_id": users[phone].id,
                "engagement": (
                    DriverEngagement.ATTACHED_TO_HIRED_VEHICLE
                    if on_rental
                    else DriverEngagement.OWN_STAFF
                ),
                "default_vehicle_id": vehicle.id,
            },
            phone=phone,
        )
        if created:
            # Target Express pays its drivers on distance, plus the unloading
            # cash. The point incentive the vendor is charged is NOT passed on -
            # that difference is retained margin.
            #
            # A driver on a rented lorry earns nothing for driving - his owner
            # pays him - but the unloading cash still comes through him, because
            # he is the one paying the labourers.
            db.add(
                DriverPayTerms(
                    driver_id=driver.id,
                    per_km_amount=Decimal("0") if on_rental else Decimal("2.50"),
                    unloading_share_percent=Decimal("100"),
                    per_trip_amount=Decimal("0"),
                    per_point_amount=Decimal("0"),
                    daily_allowance=Decimal("0"),
                    effective_from=CONTRACT_START,
                )
            )
        drivers.append(driver)
    return drivers


def seed_consignees(db: Session) -> dict[str, Consignee]:
    rows = [
        ("Kasaragod Service Centre", "9812300001", "Kasaragod", 12.4996, 74.9869),
        ("Kannur Distribution Centre", "9812300002", "Kannur", 11.8745, 75.3704),
        ("Kozhikode Service Point", "9812300003", "Kozhikode", 11.2588, 75.7804),
        ("Thrissur Dealer Outlet", "9812300004", "Thrissur", 10.5276, 76.2144),
        ("Palakkad Service Centre", "9812300005", "Palakkad", 10.7867, 76.6548),
        ("Kattappana Dealer", "9812300006", "Kattappana", 9.7486, 77.1180),
        ("TVM Distribution Centre", "9812300007", "Thiruvananthapuram", 8.5241, 76.9366),
    ]
    out: dict[str, Consignee] = {}
    for name, phone, city, lat, lng in rows:
        consignee, _ = _get_or_create(
            db,
            Consignee,
            {
                "phone": phone,
                "city": city,
                "state": "Kerala",
                "address": f"{name}, {city}, Kerala",
                "latitude": Decimal(str(lat)),
                "longitude": Decimal(str(lng)),
                "geo_confidence": GeoConfidence.APPROXIMATE,
                "type": (
                    ConsigneeType.DISTRIBUTION_CENTER
                    if "Distribution" in name
                    else ConsigneeType.RETAIL_CUSTOMER
                ),
            },
            name=name,
        )
        out[name] = consignee
    return out


def seed_freights(db: Session, masters: dict, drivers: list[Driver], consignees: dict) -> None:
    if db.execute(select(Freight).limit(1)).scalar_one_or_none() is not None:
        return

    spare = masters["divisions"]["spare"]
    warehouse = masters["warehouse"]
    vehicles = masters["vehicles"]
    names = list(consignees.values())

    # (trip_no, lr, vehicle, driver index, start km, end km, points, days ago, status)
    trips = [
        ("Y26005651", "774", "KL07CW3317", 0, 238165, 239003, 3, 6, FreightStatus.COMPLETED),
        ("Y26005695", "775", "KL41U0317", 1, 188250, 189143, 10, 5, FreightStatus.COMPLETED),
        ("Y26005775", "783", "KL07DE1129", 2, 132933, 133432, 11, 4, FreightStatus.COMPLETED),
        # Reopens 232 km above the previous close: a trip run for the other division.
        ("Y26005892", "793", "KL41U0317", 1, 189375, 190275, 7, 2, FreightStatus.COMPLETED),
        # Reopens ten kilometres BELOW the previous close: always a data error.
        ("Y26005970", "797", "KL07DE1129", 2, 133422, 133900, 10, 1, FreightStatus.COMPLETED),
        # Rented vehicle: the hire settles to Ibrahim Haji, the unloading cash
        # goes to Basheer who pays the labourers.
        ("Y26005988", "901", "KL10AL4477", 3, 88400, 88961, 6, 1, FreightStatus.COMPLETED),
        ("Y26006013", "798", "KL07CW3317", 0, 239373, 239761, 3, 0, FreightStatus.IN_TRANSIT),
    ]

    for trip_no, lr, reg, driver_idx, start_km, end_km, point_count, days_ago, status in trips:
        trip_date = date.today() - timedelta(days=days_ago)
        picked = names[:point_count] if point_count <= len(names) else names

        freight = Freight(
            trip_no=trip_no,
            lr_no=lr,
            trip_date=trip_date,
            vendor_division_id=spare.id,
            warehouse_id=warehouse.id,
            status=status,
            destination_text=", ".join(c.city or c.name for c in picked[:3]),
            point_count=point_count,
            total_km=end_km - start_km,
            dispatched_at=datetime.combine(trip_date, datetime.min.time()),
            # Completed means the vehicle is back at the origin warehouse.
            returned_at=(
                datetime.combine(trip_date, datetime.max.time())
                if status == FreightStatus.COMPLETED
                else None
            ),
            completed_at=(
                datetime.combine(trip_date, datetime.max.time())
                if status == FreightStatus.COMPLETED
                else None
            ),
        )
        db.add(freight)
        db.flush()

        for i in range(point_count):
            consignee = picked[i % len(picked)]
            delivered = status == FreightStatus.COMPLETED
            db.add(
                FreightPoint(
                    freight_id=freight.id,
                    sequence=i + 1,
                    consignee_id=consignee.id,
                    address_snapshot=consignee.address,
                    latitude=consignee.latitude,
                    longitude=consignee.longitude,
                    loaded_box_count=4,
                    delivered_box_count=4 if delivered else 0,
                    status=(
                        FreightPointStatus.DELIVERED if delivered else FreightPointStatus.LOADED
                    ),
                )
            )

        is_open = status == FreightStatus.IN_TRANSIT
        db.add(
            FreightLeg(
                freight_id=freight.id,
                sequence=1,
                vehicle_id=vehicles[reg].id,
                driver_id=drivers[driver_idx].id,
                start_odometer=start_km,
                end_odometer=None if is_open else end_km,
                leg_distance_km=None if is_open else end_km - start_km,
                started_at=datetime.combine(trip_date, datetime.min.time()),
                ended_at=None if is_open else datetime.combine(trip_date, datetime.max.time()),
                change_reason=LegChangeReason.INITIAL,
            )
        )


def main() -> None:
    db = SessionLocal()
    try:
        users = seed_users(db)
        masters = seed_masters(db)
        drivers = seed_drivers(db, users, masters["vehicles"])
        consignees = seed_consignees(db)
        seed_freights(db, masters, drivers, consignees)
        db.commit()
        print("Seed complete.")
        print("  Admin login    9000000001 / target123")
        print("  Warehouse      9000000003 / target123")
        print("  Accounts       9000000004 / target123")
        print("  Driver         9000000012 / target123   (has an open trip)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
