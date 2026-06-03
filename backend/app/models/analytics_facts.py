"""Analytics fact / aggregate relations for evaluations — populated by ``populate-analytics``.

Flat, zero-JSON leaf facts in the ``analytics`` schema:
  * ``fact_evaluation`` — one row per ``platform.evaluation_details`` (LLM verdict atom).
  * ``fact_evaluation_review`` — one row per ``platform.evaluation_review_items`` (human review atom).
  * ``agg_evaluation_run`` — per-run rollup, a MATERIALIZED VIEW rebuilt by the one populator.

Raw evidence stays in the TXN ``evaluations.raw_payload``; never denormalized here.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FactEvaluation(Base):
    """Leaf grain: one row per evaluation_detail. Flat, no JSON. Joins/filters resolve here."""

    __tablename__ = "fact_evaluation"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    detail_id: Mapped[int] = mapped_column(nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    app_id: Mapped[str] = mapped_column(Text, nullable=False)
    eval_type: Mapped[str] = mapped_column(Text, nullable=False)
    run_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # target identity + denormalized subject dims (from evaluation_targets.attributes)
    target_key: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str | None] = mapped_column(Text, nullable=True)

    # evaluator identity
    evaluator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    evaluator_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # the detail atom (discriminated by style)
    style: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    max: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(Text, nullable=True)
    locator: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_main: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reference_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_fe_run", "run_id"),
        Index("idx_fe_tenant_app", "tenant_id", "app_id"),
        Index("idx_fe_app_type_style_key", "app_id", "eval_type", "style", "key"),
        Index("idx_fe_app_lead", "app_id", "lead_id"),
        Index("idx_fe_detail", "detail_id", unique=True),
        {"schema": "analytics"},
    )


class FactEvaluationReview(Base):
    """Leaf grain: one row per evaluation_review_item (human verdict). Joins fact_evaluation on (run_id, target_key, key)."""

    __tablename__ = "fact_evaluation_review"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    review_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    review_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    review_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    target_key: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_fer_run_key", "run_id", "key"),
        Index("idx_fer_app_key", "app_id", "key"),
        Index("idx_fer_tenant_app", "tenant_id", "app_id"),
        Index("idx_fer_item", "review_item_id", unique=True),
        {"schema": "analytics"},
    )


class AggEvaluationRun(Base):
    """Per-run rollup. Backed by the ``analytics.agg_evaluation_run`` MATERIALIZED VIEW
    (created in Alembic, rebuilt by the populator). Read-only ORM mapping — never written
    directly; ``run_id`` is the unique key."""

    __tablename__ = "agg_evaluation_run"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    app_id: Mapped[str] = mapped_column(Text, nullable=False)
    eval_type: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    run_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_count: Mapped[int | None] = mapped_column(nullable=True)
    pass_count: Mapped[int | None] = mapped_column(nullable=True)
    fail_count: Mapped[int | None] = mapped_column(nullable=True)
    pass_rate: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    avg_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    rule_fail_count: Mapped[int | None] = mapped_column(nullable=True)
    critical_count: Mapped[int | None] = mapped_column(nullable=True)

    __table_args__ = ({"schema": "analytics"},)
