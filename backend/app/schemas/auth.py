import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    """Login is by phone number: it is the one identifier every role has,
    including drivers who may not have an email address."""

    phone: str = Field(min_length=6, max_length=20)
    password: str = Field(min_length=4, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone: str
    email: str | None
    role: UserRole
    is_active: bool
    # Drivers on rented vehicles log in to run the trip but are not paid by
    # Target Express, so their earnings screen is switched off. Per user, not
    # derived from the vehicle, because a driver can move between an owned and a
    # rented lorry without his visibility flipping with the roster.
    can_view_earnings: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=6, max_length=20)
    email: str | None = None
    password: str = Field(min_length=6, max_length=128)
    role: UserRole
    can_view_earnings: bool = False


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    can_view_earnings: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)
