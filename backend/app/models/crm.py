"""CRM canonical store — generic two-tier landing + core + typed slots + per-connection map.

Domain/company fields are DATA in generic slots whose meaning is set per-tenant by
``crm_field_map`` — never named columns here. Vendor lives on ``ProviderConnection``;
behaviour lives on the map. ``connection_id`` is an indexed UUID (no cross-schema FK to
``orchestration.provider_connections`` — links go orchestration→platform; app code scopes
on tenant+app+connection). All tables live in ``platform``; analytics views derive from them.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CrmSourceRecord(Base):
    """Verbatim CRM JSON landing (provenance + replay tape — re-map without re-syncing)."""
    __tablename__ = "crm_source_record"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "app_id", "connection_id", "source_object", "source_record_id",
            name="uq_crm_source_record_natural_key",
        ),
        Index("ix_crm_source_record_scope", "tenant_id", "app_id", "connection_id"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_object: Mapped[str] = mapped_column(String(128), nullable=False)
    record_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(256), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_record_hash: Mapped[Optional[str]] = mapped_column(String(64))
    first_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_seen_in_source_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class CrmLead(Base):
    """Lead core — the 19-col universal standard set (design §4). Domain fields are slots."""
    __tablename__ = "crm_lead"
    __table_args__ = (
        UniqueConstraint("tenant_id", "app_id", "lead_id", name="uq_crm_lead_business_key"),
        Index("ix_crm_lead_scope", "tenant_id", "app_id"),
        Index("ix_crm_lead_stage", "tenant_id", "app_id", "lead_stage"),
        Index("ix_crm_lead_phone_norm", "tenant_id", "app_id", "phone_number_norm"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    lead_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # identity
    first_name: Mapped[Optional[str]] = mapped_column(String(256))
    last_name: Mapped[Optional[str]] = mapped_column(String(256))
    full_name: Mapped[Optional[str]] = mapped_column(String(512))
    email: Mapped[Optional[str]] = mapped_column(String(320))
    # phone — verbatim + E.164 (shared normaliser, region IN; nullable)
    phone_number: Mapped[Optional[str]] = mapped_column(String(64))
    phone_number_norm: Mapped[Optional[str]] = mapped_column(String(32))
    # attribution
    source: Mapped[Optional[str]] = mapped_column(String(128))
    sub_source: Mapped[Optional[str]] = mapped_column(String(128))
    # pipeline (stage + lifecycle status kept separate)
    lead_stage: Mapped[Optional[str]] = mapped_column(String(128))
    lead_substage: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[Optional[str]] = mapped_column(String(128))
    lost_reason: Mapped[Optional[str]] = mapped_column(String(256))
    # ownership
    owner_id: Mapped[Optional[str]] = mapped_column(String(128))
    owner_name: Mapped[Optional[str]] = mapped_column(String(256))
    # lifecycle timestamps (source-derived; set by the unpacker, not row audit)
    converted: Mapped[Optional[bool]] = mapped_column(Boolean)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class CrmLeadExt(Base):
    """Generic typed slots, 1:1 with ``crm_lead``. Slots are cold — never indexed/queried directly."""
    __tablename__ = "crm_lead_ext"
    __table_args__ = (
        UniqueConstraint("crm_lead_id", name="uq_crm_lead_ext_one_to_one"),
        Index("ix_crm_lead_ext_scope", "tenant_id", "app_id"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crm_lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.crm_lead.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # generic typed slot pool (DQ-3): txt×30, num×20, int×20, dt×20, bool×10, json×1
    for _i in range(1, 31):
        locals()[f"txt_{_i:02d}"] = mapped_column(Text, nullable=True)
    for _i in range(1, 21):
        locals()[f"num_{_i:02d}"] = mapped_column(Numeric, nullable=True)
        locals()[f"int_{_i:02d}"] = mapped_column(BigInteger, nullable=True)
        locals()[f"dt_{_i:02d}"] = mapped_column(DateTime(timezone=True), nullable=True)
    for _i in range(1, 11):
        locals()[f"bool_{_i:02d}"] = mapped_column(Boolean, nullable=True)
    json_01: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    del _i


class CrmActivity(Base):
    """Activity (call) core — standard cols; lead-link by business ``lead_id`` (soft link)."""
    __tablename__ = "crm_activity"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "app_id", "source_activity_id", name="uq_crm_activity_natural_key",
        ),
        Index("ix_crm_activity_lead", "tenant_id", "app_id", "lead_id"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    lead_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_activity_id: Mapped[str] = mapped_column(String(256), nullable=False)
    direction: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[Optional[str]] = mapped_column(String(128))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class CrmActivityExt(Base):
    """Generic typed slots, 1:1 with ``crm_activity``. Smaller pool (standard cols cover most)."""
    __tablename__ = "crm_activity_ext"
    __table_args__ = (
        UniqueConstraint("crm_activity_id", name="uq_crm_activity_ext_one_to_one"),
        Index("ix_crm_activity_ext_scope", "tenant_id", "app_id"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crm_activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.crm_activity.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # smaller slot pool: txt×10, num×5, int×5, dt×5, bool×5, json×1
    for _i in range(1, 11):
        locals()[f"txt_{_i:02d}"] = mapped_column(Text, nullable=True)
    for _i in range(1, 6):
        locals()[f"num_{_i:02d}"] = mapped_column(Numeric, nullable=True)
        locals()[f"int_{_i:02d}"] = mapped_column(BigInteger, nullable=True)
        locals()[f"dt_{_i:02d}"] = mapped_column(DateTime(timezone=True), nullable=True)
        locals()[f"bool_{_i:02d}"] = mapped_column(Boolean, nullable=True)
    json_01: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    del _i


class CrmFieldMap(Base):
    """Per-connection mapping: source field → standard column / generic slot + value-norm."""
    __tablename__ = "crm_field_map"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "app_id", "connection_id", "record_type", "slot",
            name="uq_crm_field_map_slot",
        ),
        UniqueConstraint(
            "tenant_id", "app_id", "connection_id", "record_type", "semantic_key",
            name="uq_crm_field_map_semantic_key",
        ),
        Index("ix_crm_field_map_scope", "tenant_id", "app_id", "connection_id"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_type: Mapped[str] = mapped_column(String(16), nullable=False)
    slot: Mapped[str] = mapped_column(String(32), nullable=False)
    semantic_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_field: Mapped[str] = mapped_column(String(256), nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value_map: Mapped[Optional[dict]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    description: Mapped[Optional[str]] = mapped_column(Text)


__all__ = [
    "CrmSourceRecord",
    "CrmLead",
    "CrmLeadExt",
    "CrmActivity",
    "CrmActivityExt",
    "CrmFieldMap",
]
