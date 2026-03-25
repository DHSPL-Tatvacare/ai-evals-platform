"""Cached LSQ lead data — lazily populated on detail view."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TenantUserMixin


class LsqLeadCache(Base, TenantUserMixin):
    __tablename__ = "lsq_lead_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    prospect_id: Mapped[str] = mapped_column(String(100), nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=True, default="")
    last_name: Mapped[str] = mapped_column(String(255), nullable=True, default="")
    phone: Mapped[str] = mapped_column(String(50), nullable=True, default="")
    email: Mapped[str] = mapped_column(String(255), nullable=True, default="")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "prospect_id", name="uq_lsq_lead_cache_tenant_prospect"),
        Index("idx_lsq_lead_cache_tenant", "tenant_id"),
    )
