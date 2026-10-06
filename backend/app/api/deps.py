import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
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


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Route guard. One login serves every role; this decides what each reaches."""

    allowed = set(roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action is not available for your role",
            )
        return user

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
