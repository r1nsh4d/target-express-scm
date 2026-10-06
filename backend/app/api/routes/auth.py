from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_ROLES, get_current_user, require_roles
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def read_me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


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

    user = User(
        full_name=payload.full_name,
        phone=payload.phone,
        email=payload.email,
        role=payload.role,
        can_view_earnings=payload.can_view_earnings,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


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

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


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
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ADMIN_ROLES)),
) -> list[UserOut]:
    users = db.execute(select(User).order_by(User.full_name)).scalars().all()
    return [UserOut.model_validate(u) for u in users]
