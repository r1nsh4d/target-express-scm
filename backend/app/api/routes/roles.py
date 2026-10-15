"""Roles somebody can make, instead of six compiled into the application.

The six built-in roles are seeded here as system roles holding exactly the
capabilities they already had — a translation, not a redesign. What they gain
is company: a branch manager in Kannur who sees freights and invoices but not
settlements used to require a developer and now requires a row.

Two things on a role, and they are not the same kind of thing:

  CAPABILITIES are enforced by the route guards on the server. There are five
  because there are five distinct guards, and inventing a "Freights: delete"
  tick that no endpoint consults would be a switch wired to nothing.

  SCREENS decide what appears in the navigation. Tidiness, not security — the
  server would still answer a request made directly. The screen list is
  capped at what the capabilities could reach anyway, because an item in the
  rail with a 403 behind it is worse than no item.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_ROLES, get_current_user, require_roles
from app.core.privileges import (
    CAPABILITIES,
    SCREEN_KEYS,
    SCREENS,
    SYSTEM_ROLE_CAPABILITIES,
    screens_for,
)
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.role import Role, RoleCapability, RoleScreen
from app.models.user import User

router = APIRouter(prefix="/api", tags=["roles"])

AdminDep = Depends(require_roles(*ADMIN_ROLES))


class CapabilityOut(BaseModel):
    key: str
    label: str


class ScreenOut(BaseModel):
    key: str
    label: str
    needs: str


class RoleOut(BaseModel):
    id: str
    name: str
    description: str | None
    is_system: bool
    is_active: bool
    base_role: str | None
    capabilities: list[str]
    screens: list[str]
    user_count: int


class RoleIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    capabilities: list[str] = Field(min_length=1)
    screens: list[str] = []


def _out(db: Session, role: Role) -> RoleOut:
    users = int(
        db.scalar(select(func.count()).select_from(User).where(User.role_id == role.id)) or 0
    )
    return RoleOut(
        id=str(role.id),
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        is_active=role.is_active,
        base_role=role.base_role,
        capabilities=sorted(c.capability for c in role.capabilities),
        screens=sorted(s.screen for s in role.screens),
        user_count=users,
    )


def ensure_system_roles(db: Session) -> None:
    """Seed the six built-ins, and keep their capabilities correct.

    Re-synced on every listing rather than only at install, because the
    capability table lives in code: adding a capability to a built-in role in
    a later version has to reach a database created by an earlier one, and
    nobody is going to run a migration for a row that the code already
    describes completely.

    Only the capabilities are re-synced. The name, description and screen list
    are left alone once created, because somebody may reasonably have renamed
    "Ops Admin" to "Operations Desk" and should not find it renamed back on
    the next deploy.
    """
    existing = {
        role.base_role: role
        for role in db.execute(select(Role).where(Role.is_system.is_(True))).scalars()
    }

    for user_role, caps in SYSTEM_ROLE_CAPABILITIES.items():
        role = existing.get(user_role.value)
        if role is None:
            role = Role(
                name=user_role.value.replace("_", " ").title(),
                description="Built in. Its permissions are part of the application.",
                is_system=True,
                base_role=user_role.value,
                is_active=True,
            )
            db.add(role)
            db.flush()
            for screen in sorted(screens_for(caps)):
                db.add(RoleScreen(role_id=role.id, screen=screen))

        held = {c.capability for c in role.capabilities}
        for missing in caps - held:
            db.add(RoleCapability(role_id=role.id, capability=missing))
        for extra in held - caps:
            for row in list(role.capabilities):
                if row.capability == extra:
                    db.delete(row)

    db.commit()


@router.get("/capabilities", response_model=dict)
def list_capabilities(_=AdminDep) -> dict:
    """What a role can be given, and what each one means."""
    return {
        "capabilities": [
            CapabilityOut(key=key, label=label).model_dump()
            for key, label in CAPABILITIES.items()
        ],
        "screens": [
            ScreenOut(key=key, label=label, needs=needs).model_dump()
            for key, label, needs in SCREENS
        ],
    }


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db), _=AdminDep):
    ensure_system_roles(db)
    roles = db.execute(select(Role).order_by(Role.is_system.desc(), Role.name)).scalars()
    return [_out(db, r) for r in roles]


def _validate(payload: RoleIn) -> tuple[set[str], set[str]]:
    caps = set(payload.capabilities)
    unknown = caps - set(CAPABILITIES)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown: {', '.join(sorted(unknown))}")

    # The driver app is a different application. A login that is both a
    # driver and an administrator is a login being shared, and the moment one
    # exists nobody can say who recorded a delivery.
    from app.core.privileges import Capability

    if Capability.DRIVE in caps and len(caps) > 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "A driver role cannot also have office permissions. "
                "Make a second login instead, so it is clear who did what."
            ),
        )

    screens = set(payload.screens) & SCREEN_KEYS
    # Capped at what the capabilities could reach: an item in the rail with a
    # 403 behind it is worse than no item.
    return caps, screens & screens_for(caps)


@router.post("/roles", response_model=RoleOut, status_code=201)
def create_role(payload: RoleIn, db: Session = Depends(get_db), _=AdminDep):
    caps, screens = _validate(payload)

    name = payload.name.strip()
    clash = db.execute(
        select(Role).where(func.lower(Role.name) == name.lower())
    ).scalar_one_or_none()
    if clash is not None:
        raise HTTPException(status_code=409, detail=f"There is already a role called {name}")

    role = Role(
        name=name,
        description=(payload.description or "").strip() or None,
        is_system=False,
        is_active=True,
    )
    db.add(role)
    db.flush()
    for cap in sorted(caps):
        db.add(RoleCapability(role_id=role.id, capability=cap))
    for screen in sorted(screens or screens_for(caps)):
        db.add(RoleScreen(role_id=role.id, screen=screen))

    db.commit()
    db.refresh(role)
    return _out(db, role)


@router.patch("/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: str, payload: RoleIn, db: Session = Depends(get_db), _=AdminDep):
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")

    caps, screens = _validate(payload)

    if role.is_system and caps != {c.capability for c in role.capabilities}:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{role.name} is built in and its permissions are part of the "
                "application. Make a new role instead — editing this one is how "
                "somebody locks themselves out of the screen they would need to "
                "undo it."
            ),
        )

    role.name = payload.name.strip()
    role.description = (payload.description or "").strip() or None

    if not role.is_system:
        for row in list(role.capabilities):
            db.delete(row)
        db.flush()
        for cap in sorted(caps):
            db.add(RoleCapability(role_id=role.id, capability=cap))

    for row in list(role.screens):
        db.delete(row)
    db.flush()
    for screen in sorted(screens):
        db.add(RoleScreen(role_id=role.id, screen=screen))

    db.commit()
    db.refresh(role)
    return _out(db, role)


@router.delete("/roles/{role_id}", status_code=204)
def delete_role(role_id: str, db: Session = Depends(get_db), _=AdminDep):
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(
            status_code=409,
            detail=f"{role.name} is built in and cannot be deleted.",
        )

    # Deleting it would set role_id to null and silently drop those people
    # back to whatever their base enum says — which is not what anybody
    # intended and would not be noticed until somebody could not open a
    # screen.
    users = int(
        db.scalar(select(func.count()).select_from(User).where(User.role_id == role.id)) or 0
    )
    if users:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{users} {'person is' if users == 1 else 'people are'} on this role. "
                "Move them to another one first."
            ),
        )

    db.delete(role)
    db.commit()
    from fastapi import Response

    return Response(status_code=204)


class MyAccessOut(BaseModel):
    role_name: str
    capabilities: list[str]
    screens: list[str]


@router.get("/me/access", response_model=MyAccessOut)
def my_access(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MyAccessOut:
    # Any signed-in person, deliberately — this is the question "what may I
    # do", and guarding it with a capability would mean the people with the
    # fewest permissions could not find out what theirs are.
    #
    # Not require_roles(*every role) either, which is what this said first:
    # the guard requires what its roles have in common, and a driver shares
    # nothing with an accountant, so that intersection is empty and it
    # refused everybody.
    """What the signed-in person may do, for the navigation to read.

    Served rather than inferred in the browser: the rail should show what the
    server will actually allow, and a client-side guess at that is a guess
    that goes stale the moment a role changes.
    """
    from app.api.deps import capabilities_of

    caps = capabilities_of(user)
    role = user.custom_role
    if role is not None and role.is_active:
        screens = sorted(s.screen for s in role.screens)
        name = role.name
    else:
        screens = sorted(screens_for(caps))
        name = user.role.replace("_", " ").title()

    return MyAccessOut(role_name=name, capabilities=sorted(caps), screens=screens)
