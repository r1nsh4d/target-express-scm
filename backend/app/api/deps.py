import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.core.privileges import capabilities_for_role
from app.models.enums import UserRole
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    if payload is None or not payload.get("sub"):
        raise CREDENTIALS_ERROR

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise CREDENTIALS_ERROR from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR
    return user


def capabilities_of(user: User) -> set[str]:
    """What this user may do.

    A custom role's capabilities if they are on one, otherwise the built-in
    role's. Two sources and one answer, so every guard asks the same question
    whichever kind of role somebody has.
    """
    role = getattr(user, "custom_role", None)
    if role is not None and role.is_active:
        return {row.capability for row in role.capabilities}
    return capabilities_for_role(user.role)


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Route guard, written in roles and enforced in capabilities.

    Sixty endpoints are written as "one of these roles", and rewriting all of
    them to name a capability would be a large change to code that works. So
    the guard translates instead: the roles it was given imply a set of
    capabilities, and a user passes if they hold any of them.

    For the six built-in roles this is exactly the old behaviour — the
    translation table in core.privileges is derived from these same groupings,
    so Warehouse Admin reaches today what Warehouse Admin reached yesterday.
    What it adds is that a role somebody made, holding `operations.manage`,
    now passes a guard written as `require_roles(*WAREHOUSE_ROLES)` without
    that guard having to know custom roles exist.
    """

    allowed = set(roles)

    # What this endpoint actually requires: the capabilities every one of its
    # accepted roles has IN COMMON, all of which are then required.
    #
    # The union is wrong, and wrong in the dangerous direction. Super Admin
    # appears in every grouping and holds everything, so unioning makes every
    # guard accept every capability — a role with nothing but `office.view`
    # would have passed the money guard. The first version of this did exactly
    # that, and the test for a branch manager reaching Money in caught it.
    #
    # The intersection is the distinguishing requirement. ACCOUNTS_ROLES is
    # Super Admin and Accounts; what they share is office.view and
    # money.manage, and needing both is precisely what "may touch the money"
    # means. It fails closed: a capability a grouping does not unanimously
    # imply is not granted by it.
    required: set[str] = set()
    for i, role in enumerate(allowed):
        caps = capabilities_for_role(role)
        required = caps if i == 0 else required & caps

    def dependency(user: User = Depends(get_current_user)) -> User:
        # A built-in role on a user with no custom role passes directly.
        # Cheaper, and it means a mistake in the capability table can never
        # lock out the people who would have to correct it.
        if user.role in allowed and getattr(user, "role_id", None) is None:
            return user

        held = capabilities_of(user)
        if required and required <= held:
            return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is not available for your role",
        )

    return dependency


def require_capability(*capabilities: str) -> Callable[[User], User]:
    """Guard written directly in capabilities, for anything new.

    Preferred over require_roles from here on: it says what the endpoint needs
    rather than who happens to have it today.
    """

    wanted = set(capabilities)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if wanted <= capabilities_of(user):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is not available for your role",
        )

    return dependency


# Common groupings, named for how the business talks about them.
ADMIN_ROLES = (UserRole.SUPER_ADMIN, UserRole.OPS_ADMIN)
WAREHOUSE_ROLES = (UserRole.SUPER_ADMIN, UserRole.OPS_ADMIN, UserRole.WAREHOUSE_ADMIN)
ACCOUNTS_ROLES = (UserRole.SUPER_ADMIN, UserRole.ACCOUNTS)
BACK_OFFICE_ROLES = (
    UserRole.SUPER_ADMIN,
    UserRole.OPS_ADMIN,
    UserRole.WAREHOUSE_ADMIN,
    UserRole.ACCOUNTS,
    UserRole.STAKEHOLDER,
)
