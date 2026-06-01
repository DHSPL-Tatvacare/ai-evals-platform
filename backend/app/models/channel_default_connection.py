"""ChannelDefaultConnection ORM — orchestration.channel_default_connections.

The default provider connection to use for a channel (whatsapp, voice, …) when
an authoring request names a channel but not a specific connection. Rung 2 of
the resolve_connection ladder. Channel is explicit here (not derived from the
provider-keyed provider_connections row), so a tenant with two whatsapp
providers can pick which one is the default.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChannelDefaultConnection(Base):
    __tablename__ = "channel_default_connections"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "app_id", "channel",
            name="uq_channel_default_connections_scope_channel",
        ),
        {"schema": "orchestration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orchestration.provider_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


__all__ = ["ChannelDefaultConnection"]
