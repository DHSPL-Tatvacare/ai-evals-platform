"""Per-(tenant, app) LLM-generated orchestration-signal snapshots."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, desc, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrchestrationSignalSnapshot(Base):
    """Latest LLM-generated orchestration-signal snapshot per (tenant, app).

    Produced by a scheduled job; the analytics dashboard reads the most recent
    row for the tenant + app. ``signals`` is a list of signal objects.
    """

    __tablename__ = "orchestration_signal_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    period: Mapped[str | None] = mapped_column(Text, nullable=True)
    signals: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_orchestration_signal_snapshot_recent",
            "tenant_id",
            "app_id",
            desc("generated_at"),
        ),
        {"schema": "analytics"},
    )
