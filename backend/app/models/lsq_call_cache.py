"""Cached LSQ call records — avoids repeated lead hydration API calls."""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TenantUserMixin


class LsqCallCache(Base, TenantUserMixin):
    __tablename__ = "lsq_call_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    activity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    prospect_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    agent_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    event_code: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    call_start_time: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recording_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    display_number: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    call_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    call_session_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    created_on: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    lead_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "activity_id", name="uq_lsq_call_cache_tenant_activity"),
        Index("idx_lsq_call_cache_tenant", "tenant_id"),
    )
