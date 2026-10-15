import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class Role(BaseModel):
    """A named set of capabilities, and the screens that go with it.

    The six built-in roles are seeded here as system roles holding exactly the
    capabilities they already had, so nothing about them changes. What they
    gain is company: a branch manager in Kannur who sees freights and invoices
    but not settlements is now a row rather than a developer's afternoon.

    A system role cannot be deleted or have its capabilities edited. Its
    screen list can be, because that is presentation — but the capability set
    is what every guard in the application is written against, and editing
    SUPER_ADMIN to drop `admin.manage` is how somebody locks themselves out of
    the screen they would need to undo it.
    """

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("name", name="uq_role_name"),)

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # One of the six built-ins. These are referenced by name in code and
    # seeded on every deploy, so they are protected from deletion.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # Which built-in this corresponds to, for a system role. Null for one
    # somebody made. It is what a user's effective UserRole falls back to, so
    # that the existing enum-shaped checks still have an answer.
    base_role: Mapped[str | None] = mapped_column(String(24))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    capabilities: Mapped[list["RoleCapability"]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )
    screens: Mapped[list["RoleScreen"]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


class RoleCapability(BaseModel):
    """One capability granted to a role.

    A row per grant rather than a JSON blob, so "which roles can touch money"
    is a query rather than a scan — the question somebody asks the week after
    an argument about who changed a settlement.
    """

    __tablename__ = "role_capabilities"
    __table_args__ = (
        UniqueConstraint("role_id", "capability", name="uq_role_capability"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability: Mapped[str] = mapped_column(String(48), nullable=False)

    role: Mapped[Role] = relationship(back_populates="capabilities")


class RoleScreen(BaseModel):
    """One screen this role sees in the navigation.

    Presentation, not security — the server enforces capabilities, and a
    screen left off a role is tidiness rather than a lock. Said plainly here
    so nobody reads the tick box as something it is not.
    """

    __tablename__ = "role_screens"
    __table_args__ = (UniqueConstraint("role_id", "screen", name="uq_role_screen"),)

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    screen: Mapped[str] = mapped_column(String(48), nullable=False)

    role: Mapped[Role] = relationship(back_populates="screens")
