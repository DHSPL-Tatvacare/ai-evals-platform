"""Analytics fact / aggregate relations for workflow dispatch — populated by ``populate-workflow-analytics``.

Flat, zero-JSON relations in the ``analytics`` schema:
  * ``fact_workflow_engagement`` — one row per (run × recipient × capability); the populator collapses a
    recipient's many action rows on a channel into one engagement row (most-advanced ``outcome_bucket``).
  * ``agg_workflow_run`` — per-run rollup, a MATERIALIZED VIEW rebuilt by the same populator, with each
    recipient collapsed to ONE most-advanced bucket across capabilities (no double-count).

Vendor ``action_type`` stays in the TXN ``workflow_run_recipient_actions``; analytics sees only generic
``capability`` + ``outcome_bucket``. Raw payloads are never denormalized here.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FactWorkflowEngagement(Base):
    """Leaf grain: one row per (run × recipient × capability). Flat, zero JSON."""

    __tablename__ = "fact_workflow_engagement"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)

    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workflow_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workflow_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    recipient_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # dim_lead bridge (CRM apps): == recipient_id when the cohort id_column is the lead id.
    # Matches analytics.dim_lead.lead_id which is varchar(128) (holds non-UUID ids too).
    lead_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_e164: Mapped[str | None] = mapped_column(Text, nullable=True)

    capability: Mapped[str] = mapped_column(String(32), nullable=False)  # voice|messaging|webhook (generic)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)     # voice|whatsapp|webhook (data)

    connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    connection_label: Mapped[str | None] = mapped_column(Text, nullable=True)  # NULL connection → 'unmapped'
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)

    outcome_bucket: Mapped[str] = mapped_column(String(16), nullable=False)  # most-advanced for this capability
    # True iff a real bucket (rank≥1) was observed; pure-dispatch recipients default outcome_bucket
    # to the in_flight sentinel with bucket_resolved=False so rollups leave them uncounted (read_service parity).
    bucket_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    dispatched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dispatch_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # COUNT(parent_action_id IS NULL)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)           # total action rows

    cost: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    cost_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)          # avg_cost denominator
    duration_sec: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)     # SUM over positive rows
    talk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)         # COUNT over positive rows

    provider_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    triggered_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    run_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cohort_size_at_entry: Mapped[int | None] = mapped_column(Integer, nullable=True)

    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "recipient_id", "capability", name="uq_fwe_run_recipient_capability"),
        Index("idx_fwe_tenant_app", "tenant_id", "app_id"),
        Index("idx_fwe_app_workflow_started", "app_id", "workflow_id", "run_started_at"),
        Index("idx_fwe_app_channel_started", "app_id", "channel", "run_started_at"),
        Index("idx_fwe_run", "run_id"),
        Index("idx_fwe_app_recipient", "app_id", "recipient_id"),
        Index("idx_fwe_app_lead", "app_id", "lead_id"),
        {"schema": "analytics"},
    )


class AggWorkflowRun(Base):
    """Per-run rollup. Backed by the ``analytics.agg_workflow_run`` MATERIALIZED VIEW (created in Alembic,
    rebuilt by the one populator). Read-only ORM mapping — never written directly; each recipient is
    collapsed to ONE most-advanced bucket across capabilities. ``run_id`` is the unique key."""

    __tablename__ = "agg_workflow_run"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workflow_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    triggered_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    run_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cohort_size_at_entry: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    recipients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    positive: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reached: Mapped[int | None] = mapped_column(Integer, nullable=True)
    no_response: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    in_flight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dispatched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Numeric, nullable=True)

    __table_args__ = ({"schema": "analytics"},)
