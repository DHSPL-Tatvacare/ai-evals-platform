"""IdentityInviteLinkUse — one row per redemption of an invite link.

Forensic completeness (design-spec §3.1, §5.3): the legacy ``uses_count``
counter on ``identity_invite_links`` only knows *how many*, never *who*.
This table writes one row per signup so we can answer "who redeemed this
invite, when, and from what IP cluster" without leaking raw IPs.

``user_id`` is ``ON DELETE SET NULL`` so the audit row outlives the user
account it created; ``user_email_snapshot`` preserves the address.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, String, desc, text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IdentityInviteLinkUse(Base):
    __tablename__ = "identity_invite_link_uses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invite_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.identity_invite_links.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_email_snapshot: Mapped[str] = mapped_column(String(320), nullable=False)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip_hash: Mapped[Optional[str]] = mapped_column(CHAR(64), nullable=True)

    __table_args__ = (
        Index("idx_invite_uses_invite_id", "invite_link_id", desc("used_at")),
        Index(
            "idx_invite_uses_user_id",
            "user_id",
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        {"schema": "platform"},
    )
