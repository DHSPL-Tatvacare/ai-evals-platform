"""Unified evaluation TXN spine — Run → Target → Evaluation → Detail."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EvaluationTarget(Base):
    """A thing judged in a run (call / chat thread / transcript / test case). 1 run → many targets."""
    __tablename__ = "evaluation_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    target_key: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)  # call|chat_thread|transcript|test_case
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # subject metadata; flattened in analytics

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="target", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("run_id", "target_key", name="uq_evaluation_targets_run_target"),
        Index("idx_evaluation_targets_tenant_app", "tenant_id", "app_id"),
        {"schema": "platform"},
    )


class Evaluation(Base):
    """One evaluator's verdict on one target. 1 target → 1..N evaluators."""
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.evaluation_targets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(50), nullable=False)

    evaluator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    evaluator_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {name, version, output_schema_hash}
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ok|error|skipped

    headline_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    headline_max: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # prompt/raw req/resp — provenance only

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    target: Mapped["EvaluationTarget"] = relationship(back_populates="evaluations")
    details: Mapped[list["EvaluationDetail"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("idx_evaluations_evaluator", "evaluator_id"),
        {"schema": "platform"},
    )


class EvaluationDetail(Base):
    """The universal atom, discriminated by style: dimension | rule | comparison."""
    __tablename__ = "evaluation_details"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_id: Mapped[str] = mapped_column(String(50), nullable=False)

    style: Mapped[str] = mapped_column(String(16), nullable=False)  # dimension|rule|comparison
    key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    max: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # PASS|FAIL|NA (rules)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)  # minor|moderate|critical (comparisons)
    locator: Mapped[str | None] = mapped_column(Text, nullable=True)  # segment:N / api_field
    is_main: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weight: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    reference_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    evaluation: Mapped["Evaluation"] = relationship(back_populates="details")

    __table_args__ = (
        Index("idx_evaluation_details_run_style_key", "run_id", "style", "key"),
        Index("idx_evaluation_details_tenant_app_style_key", "tenant_id", "app_id", "style", "key"),
        {"schema": "platform"},
    )
