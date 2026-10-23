from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_ROLES, get_current_user, require_roles
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.enums import DriverEngagement, UserRole
from app.models.fleet import Driver, VehicleOwner
from app.models.role import Role
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _belongs_to(db: Session, user: User) -> str | None:
    """Whose login this is, when it is not Target Express's."""
    if user.vendor_id is not None:
        vendor = db.get(Vendor, user.vendor_id)
        return vendor.name if vendor else None
    if user.vehicle_owner_id is not None:
        owner = db.get(VehicleOwner, user.vehicle_owner_id)
        return owner.name if owner else None
    return None


# Roles that belong to somebody outside Target Express, and what each needs
# to be tied to. A login of one of these kinds without its tie reaches
# nothing and reads, to the person holding it, as broken.
OUTSIDE_TIES: dict[UserRole, str] = {
    UserRole.VENDOR: "vendor_id",
    UserRole.VEHICLE_OWNER: "vehicle_owner_id",
    UserRole.OWNER_DRIVER: "vehicle_owner_id",
}


def _check_ties(role: UserRole, vendor_id, vehicle_owner_id, db: Session) -> None:
    """The tie has to match the role, both ways round.

    An outside login without one is refused rather than created, because the
    alternative is a vendor signing in to a screen that tells them their
    account is not set up — which is our mistake arriving as their problem.

    An INSIDE login carrying one is refused for a different reason: nothing
    in the office scopes queries by it, so it would be a rule that looks like
    it is enforced and is not.
    """
    needed = OUTSIDE_TIES.get(role)

    if needed == "vendor_id":
        if vendor_id is None:
            raise HTTPException(
                status_code=422,
                detail="A vendor login has to say which vendor it is for.",
            )
        if db.get(Vendor, vendor_id) is None:
            raise HTTPException(status_code=404, detail="That vendor does not exist")
    elif needed == "vehicle_owner_id":
        if vehicle_owner_id is None:
            raise HTTPException(
                status_code=422,
                detail="This login has to say which vehicle owner it is for.",
            )
        if db.get(VehicleOwner, vehicle_owner_id) is None:
            raise HTTPException(
                status_code=404, detail="That vehicle owner does not exist"
            )
    elif vendor_id is not None or vehicle_owner_id is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Only a vendor or vehicle-owner login can be tied to one. An office "
                "login sees the whole business, and tying it to a vendor would look "
                "like a restriction without being one."
            ),
        )


def _ensure_driver_record(db: Session, user: User) -> None:
    """An owner-driver with no driver record cannot run a trip.

    The driver app finds the man holding the phone by looking up a Driver
    whose `user_id` is his. Without one the login signs in, shows no trips,
    and looks broken — so the record is made here rather than left as a
    second step somebody has to know about.

    An existing driver on the same phone number is linked rather than
    duplicated: that is the same man, already on the roster.
    """
    existing = db.execute(
        select(Driver).where(Driver.user_id == user.id)
    ).scalars().first()
    if existing is not None:
        return

    by_phone = db.execute(
        select(Driver).where(Driver.phone == user.phone)
    ).scalars().first()
    if by_phone is not None:
        by_phone.user_id = user.id
        return

    db.add(
        Driver(
            name=user.full_name,
            phone=user.phone,
            # He is paid by himself as the vehicle's owner, not by us.
            engagement=DriverEngagement.ATTACHED_TO_HIRED_VEHICLE,
            user_id=user.id,
            is_active=True,
        )
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """One portal for admins, accounts, drivers and stakeholders.

    The role on the token decides what the client shows and what the API allows.
    """
    user = db.execute(select(User).where(User.phone == payload.phone)).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone number or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated",
        )

    token = create_access_token(subject=str(user.id), role=str(user.role))
    return TokenResponse(access_token=token, user=UserOut.of(user))


@router.get("/me", response_model=UserOut)
def read_me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.of(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    user.hashed_password = hash_password(payload.new_password)
    db.commit()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ADMIN_ROLES)),
) -> UserOut:
    exists = db.execute(select(User).where(User.phone == payload.phone)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this phone number already exists",
        )

    # A role somebody made decides what this person reaches. The enum is
    # still set, because it is the base everything falls back to and because
    # a role can be deleted out from under a user.
    base = payload.role
    if payload.role_id is not None:
        role = db.get(Role, payload.role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="That role does not exist")
        if not role.is_active:
            raise HTTPException(status_code=409, detail=f"{role.name} is not in use")
        if role.base_role:
            base = UserRole(role.base_role)

    _check_ties(base, payload.vendor_id, payload.vehicle_owner_id, db)

    user = User(
        full_name=payload.full_name,
        phone=payload.phone,
        email=payload.email,
        role=base,
        role_id=payload.role_id,
        can_view_earnings=payload.can_view_earnings,
        vendor_id=payload.vendor_id,
        vehicle_owner_id=payload.vehicle_owner_id,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()

    if base == UserRole.OWNER_DRIVER:
        _ensure_driver_record(db, user)

    db.commit()
    db.refresh(user)
    return UserOut.of(user, _belongs_to(db, user))


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ADMIN_ROLES)),
) -> UserOut:
    """Change a user's role, status, or whether they can see their earnings."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    data = payload.model_dump(exclude_unset=True)

    # Moving somebody onto a custom role, or off one. Handled before the
    # blanket setattr below because clear_role is not a column and because
    # the base enum has to follow the role rather than be left behind
    # pointing at whatever they used to be.
    clear = data.pop("clear_role", False)
    role_id = data.pop("role_id", None)

    if clear:
        user.role_id = None
    elif role_id is not None:
        role = db.get(Role, role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="That role does not exist")
        if not role.is_active:
            raise HTTPException(status_code=409, detail=f"{role.name} is not in use")
        user.role_id = role.id
        if role.base_role:
            user.role = UserRole(role.base_role)

    for field, value in data.items():
        setattr(user, field, value)

    # Checked against what the user ENDS UP as, not what was sent, because a
    # role and a tie can move in the same request — switching a driver to an
    # owner-driver is exactly that, and validating the payload alone would
    # miss the half that was already on the record.
    _check_ties(user.role, user.vendor_id, user.vehicle_owner_id, db)

    if user.role == UserRole.OWNER_DRIVER:
        _ensure_driver_record(db, user)

    db.commit()
    db.refresh(user)
    return UserOut.of(user, _belongs_to(db, user))


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


@router.post("/users/{user_id}/reset-password", response_model=UserOut)
def reset_password(
    user_id: str,
    payload: ResetPasswordIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ADMIN_ROLES)),
) -> UserOut:
    """Set another user's password.

    Drivers lose phones and forget passwords, and there is no email on most of
    these accounts to send a reset link to - the phone number IS the username.
    Without this the only recovery is a shell on the server, which means every
    forgotten password becomes a call to whoever has SSH.

    An admin is NOT shown the old password, because nobody can be: they are
    bcrypt hashes. This sets a new one.

    Deliberately a separate endpoint from PATCH /users/{id} rather than another
    optional field on it. A password change is not the same kind of act as
    ticking "can view earnings", it is the one that hands someone an account,
    and it should be impossible to do by accident while editing something else.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # An admin resetting their own password here would skip the current-password
    # check that /change-password enforces. Send them to the right door.
    if str(user.id) == str(actor.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use Change password for your own account - it asks for your current one.",
        )

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return UserOut.of(user)


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ADMIN_ROLES)),
) -> list[UserOut]:
    users = db.execute(select(User).order_by(User.full_name)).scalars().all()
    return [UserOut.of(u, _belongs_to(db, u)) for u in users]
