"""IdentityInviteLink model — shareable signup links created by admins."""
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    ForeignKey,
    DateTime,
    Index,
    Enum as SAEnum,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import ColumnElement

from app.models.base import Base


class InviteStatus(str, enum.Enum):
    """Canonical lifecycle state for an invite link."""
    active = "active"
    revoked = "revoked"
    expired = "expired"
    exhausted = "exhausted"


class InviteSignupMethod(str, enum.Enum):
    """Signup path the invite pre-authorizes. ``sso`` is reserved for the
    SSO migration; only ``password`` is accepted by the signup route today."""
    password = "password"
    sso = "sso"


_INVITE_STATUS_ENUM = SAEnum(
    InviteStatus,
    name="invite_link_status",
    schema="platform",
    create_type=False,
    native_enum=True,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)
_INVITE_SIGNUP_METHOD_ENUM = SAEnum(
    InviteSignupMethod,
    name="invite_signup_method",
    schema="platform",
    create_type=False,
    native_enum=True,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class IdentityInviteLink(Base):
    __tablename__ = "identity_invite_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.access_roles.id"), nullable=False
    )
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uses_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[InviteStatus] = mapped_column(
        _INVITE_STATUS_ENUM,
        nullable=False,
        default=InviteStatus.active,
        server_default="active",
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_by_email_snapshot: Mapped[Optional[str]] = mapped_column(
        String(320), nullable=True
    )
    created_by_email_snapshot: Mapped[Optional[str]] = mapped_column(
        String(320), nullable=True
    )
    signup_method: Mapped[InviteSignupMethod] = mapped_column(
        _INVITE_SIGNUP_METHOD_ENUM,
        nullable=False,
        default=InviteSignupMethod.password,
        server_default="password",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_identity_invite_links_token_hash", "token_hash"),
        Index("idx_identity_invite_links_tenant", "tenant_id"),
        {"schema": "platform"},
    )

    @property
    def is_revoked(self) -> bool:
        """True iff the row has been admin-revoked. Sourced from
        ``revoked_at`` per design-spec §7.1."""
        return self.revoked_at is not None

    @classmethod
    def usable_filter(cls) -> ColumnElement[bool]:
        """SQL predicate matching links that are still redeemable.

        Post-Phase-4: the ``status`` enum is the sole source of truth.
        Lazy correction in the list route keeps this predicate honest
        for ``expired`` / ``exhausted`` rows that haven't been flipped
        on the row yet.
        """
        return cls.status == InviteStatus.active
