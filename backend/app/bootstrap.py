"""Minimum setup to walk the workflow end to end.

Creates exactly what is needed to log in and start building trips, and nothing
else - no vendors, no customers, no trips. Those get created through the
application, which is the point of the exercise.

    python -m app.bootstrap

Creates:
    - a super admin       9000000001
    - an operations admin 9000000002
    - a driver            9000000010  (with a login and pay terms)
    - one owned vehicle   KL07AA1234
    - a DOST vehicle type

For demo data with Godrej masters and worked trips, use `python -m app.seed`
instead.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import DriverEngagement, UserRole, VehicleOwnership
from app.models.fleet import Driver, DriverPayTerms, Vehicle, VehicleType
from app.models.user import User

PASSWORD = "target123"

USERS = [
    ("Super Admin", "9000000001", UserRole.SUPER_ADMIN, True),
    ("Operations Admin", "9000000002", UserRole.OPS_ADMIN, True),
    ("Rajesh K", "9000000010", UserRole.DRIVER, True),
]

VEHICLE_NO = "KL07AA1234"
DRIVER_PHONE = "9000000010"


def _get_or_create(db: Session, model, defaults: dict | None = None, **lookup):
    obj = db.execute(select(model).filter_by(**lookup)).scalar_one_or_none()
    if obj is not None:
        return obj, False
    obj = model(**lookup, **(defaults or {}))
    db.add(obj)
    db.flush()
    return obj, True


def main() -> None:
    db = SessionLocal()
    try:
        users: dict[str, User] = {}
        for name, phone, role, can_view_earnings in USERS:
            user, _ = _get_or_create(
                db,
                User,
                {
                    "full_name": name,
                    "role": role,
                    "can_view_earnings": can_view_earnings,
                    "hashed_password": hash_password(PASSWORD),
                },
                phone=phone,
            )
            users[phone] = user

        vtype, _ = _get_or_create(db, VehicleType, {"capacity_kg": 1250}, name="DOST")

        vehicle, _ = _get_or_create(
            db,
            Vehicle,
            {
                "vehicle_type_id": vtype.id,
                "ownership": VehicleOwnership.OWNED,
                "last_closing_km": 0,
                "lr_next_number": 1,
            },
            registration_no=VEHICLE_NO,
        )

        driver, created = _get_or_create(
            db,
            Driver,
            {
                "name": "Rajesh K",
                "user_id": users[DRIVER_PHONE].id,
                "engagement": DriverEngagement.OWN_STAFF,
                "default_vehicle_id": vehicle.id,
            },
            phone=DRIVER_PHONE,
        )
        if created:
            # Paid on distance plus the unloading cash, which is how Target
            # Express actually pays its drivers.
            db.add(
                DriverPayTerms(
                    driver_id=driver.id,
                    per_km_amount=Decimal("2.50"),
                    unloading_share_percent=Decimal("100"),
                    effective_from=date.today(),
                )
            )

        db.commit()

        print("Bootstrap complete.\n")
        print(f"  {'Role':<20} {'Login':<14} Password")
        print(f"  {'-' * 20} {'-' * 14} {'-' * 10}")
        for _name, phone, role, _flag in USERS:
            print(f"  {role.replace('_', ' ').title():<20} {phone:<14} {PASSWORD}")
        print(f"\n  Vehicle: {VEHICLE_NO} (owned, DOST)")
        print(f"  Driver:  {driver.name}, Rs 2.50/km + unloading\n")
        print("  Next: sign in as the admin and create a vendor, then a trip.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
