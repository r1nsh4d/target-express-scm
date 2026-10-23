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
    # The role somebody made, when this user is on one. The enum above stays
    # as the base, so everything already written against it still has an
    # answer.
    role_id: uuid.UUID | None = None
    # Filled from the relationship so a list of users can show which role
    # each is on without a second request per row.
    role_name: str | None = None
    # Whether this login is shown money at all.
    #
    # A driver on a rented vehicle is paid by his vehicle's owner, not by
    # Target Express, so there is no figure of ours to show him. His app
    # leaves the earnings tab out entirely rather than opening it onto a
    # refusal — a locked door he can see is still a question he will ask.
    # Per user rather than derived from the vehicle, because a driver can
    # move between an owned and a rented lorry without his visibility
    # flipping with the roster.
    can_view_earnings: bool = False
    # The vendor or vehicle owner this login belongs to, when it is not ours.
    vendor_id: uuid.UUID | None = None
    vehicle_owner_id: uuid.UUID | None = None
    # Their name, so a list of logins can say whose each one is without a
    # lookup per row.
    belongs_to: str | None = None

    @classmethod
    def of(cls, user, belongs_to: str | None = None) -> "UserOut":
        """With the custom role's name resolved, and whose login it is.

        Done here rather than at each call site, because a user list that
        shows the enum where a custom role applies tells the administrator
        the opposite of what they configured.
        """
        out = cls.model_validate(user)
        role = getattr(user, "custom_role", None)
        out.role_name = role.name if role is not None else None
        out.belongs_to = belongs_to
        return out


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=6, max_length=20)
    email: str | None = None
    password: str = Field(min_length=6, max_length=128)
    # One or the other. A role_id is the modern way and carries the
    # capabilities; the enum is kept for the built-in six and as the base a
    # custom role falls back to.
    role: UserRole
    role_id: uuid.UUID | None = None
    can_view_earnings: bool = False
    # Who this login belongs to, when it is not Target Express.
    #
    # Required for the outside roles and refused for the inside ones. A
    # vendor login with no vendor on it reaches nothing and reads as broken;
    # an office login carrying one is a scoping rule nobody wrote.
    vendor_id: uuid.UUID | None = None
    vehicle_owner_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: str | None = None
    role: UserRole | None = None
    # Sent as null to take somebody off a custom role and back to their
    # built-in one, which is why it is a sentinel rather than "omitted means
    # unchanged" like the rest.
    role_id: uuid.UUID | None = None
    clear_role: bool = False
    is_active: bool | None = None
    can_view_earnings: bool | None = None
    vendor_id: uuid.UUID | None = None
    vehicle_owner_id: uuid.UUID | None = None
    can_view_earnings: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)
