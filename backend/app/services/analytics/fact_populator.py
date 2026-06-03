"""Fact population — ONE generic path: TXN eval spine + review tables → flat analytics facts.

Reads the unified spine (``platform.evaluation_details`` → ``evaluations`` → ``evaluation_targets``)
and the human-review tables; writes the flat leaf facts ``analytics.fact_evaluation`` +
``fact_evaluation_review`` and refreshes the ``agg_evaluation_run`` matview. No per-eval_type
extractors, no JSON. The pre-existing ``fact_lead_signal`` write path (step 8) is preserved as-is.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics_facts import FactEvaluation, FactEvaluationReview
from app.models.analytics_lead_facts import FactLeadSignal
from app.models.analytics_log import LogFactPopulationRun
from app.models.eval_run import EvaluationRun, EvaluationRunThreadResult
from app.models.evaluation import Evaluation, EvaluationDetail, EvaluationTarget
from app.models.review import EvaluationReview, EvaluationReviewItem
from app.services.analytics.signal_derivation.base import StrategyContext
from app.services.analytics.signal_derivation.persistence import derived_signal_to_fact_row
from app.services.analytics.signal_derivation.registry import get_strategy
from app.services.analytics.signal_derivation.resolution import resolve_effective_definition
from app.services.analytics.types import PopulationResult

logger = logging.getLogger(__name__)


def _as_uuid(value) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


class FactPopulator:
    """Rebuilds analytics facts for one eval run from the TXN spine. Idempotent per run."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def populate(self, run_id: UUID) -> PopulationResult:
        start = time.monotonic()
        log: LogFactPopulationRun | None = None
        try:
            run = await self._load_run(run_id)
            if not run:
                raise ValueError(f"EvaluationRun {run_id} not found")

            log = LogFactPopulationRun(
                run_id=run_id, app_id=run.app_id, tenant_id=run.tenant_id,
                job_type="populate_facts", status="running",
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(log)
            await self.db.flush()

            deleted = await self._delete_existing(run_id)
            rows = await self._populate_eval_facts(run)
            rows += await self._populate_review_facts(run)
            rows += await self._populate_lead_signals(run)
            await self._refresh_rollup()

            elapsed = (time.monotonic() - start) * 1000
            log.status = "completed"
            log.rows_inserted = rows
            log.rows_deleted = deleted
            log.duration_ms = elapsed
            log.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            logger.info("Populated analytics for run %s: %d rows in %.0fms", run_id, rows, elapsed)
            return PopulationResult(run_id=run_id, rows_inserted=rows, duration_ms=elapsed, errors=[])
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.error("Analytics population failed for run %s: %s", run_id, e, exc_info=True)
            try:
                if log is not None:
                    log.status = "failed"
                    log.error_message = str(e)[:2000]
                    log.duration_ms = elapsed
                    log.completed_at = datetime.now(timezone.utc)
                    await self.db.commit()
                else:
                    await self.db.rollback()
            except Exception:
                await self.db.rollback()
            raise

    async def _load_run(self, run_id: UUID) -> EvaluationRun | None:
        return (await self.db.execute(
            select(EvaluationRun).where(EvaluationRun.id == run_id)
        )).scalar_one_or_none()

    async def _populate_eval_facts(self, run: EvaluationRun) -> int:
        """One fact_evaluation row per evaluation_detail, flattened from the spine."""
        rows = (await self.db.execute(
            select(EvaluationDetail, Evaluation, EvaluationTarget)
            .join(Evaluation, Evaluation.id == EvaluationDetail.evaluation_id)
            .join(EvaluationTarget, EvaluationTarget.id == Evaluation.target_id)
            .where(EvaluationDetail.run_id == run.id)
        )).all()
        count = 0
        for detail, evaluation, target in rows:
            attrs = target.attributes if isinstance(target.attributes, dict) else {}
            ref = evaluation.evaluator_ref if isinstance(evaluation.evaluator_ref, dict) else {}
            self.db.add(FactEvaluation(
                detail_id=detail.id,
                evaluation_id=evaluation.id,
                target_id=target.id,
                run_id=run.id,
                tenant_id=run.tenant_id,
                user_id=run.user_id,
                app_id=run.app_id,
                eval_type=run.eval_type,
                run_completed_at=run.completed_at,
                target_key=target.target_key,
                target_type=target.target_type,
                lead_id=_as_uuid(attrs.get("lead_id")),
                agent=attrs.get("agent"),
                direction=attrs.get("direction"),
                evaluator_id=evaluation.evaluator_id,
                evaluator_name=ref.get("name"),
                style=detail.style,
                key=detail.key,
                label=detail.label,
                score=detail.score,
                max=detail.max,
                status=detail.status,
                severity=detail.severity,
                locator=detail.locator,
                is_main=detail.is_main,
                reference_text=detail.reference_text,
                candidate_text=detail.candidate_text,
                explanation=detail.explanation,
            ))
            count += 1
        await self.db.flush()
        return count

    async def _populate_review_facts(self, run: EvaluationRun) -> int:
        """One fact_evaluation_review row per evaluation_review_item for this run."""
        rows = (await self.db.execute(
            select(EvaluationReviewItem, EvaluationReview)
            .join(EvaluationReview, EvaluationReview.id == EvaluationReviewItem.review_id)
            .where(EvaluationReview.run_id == run.id)
        )).all()
        count = 0
        for item, review in rows:
            self.db.add(FactEvaluationReview(
                review_item_id=item.id,
                review_id=review.id,
                run_id=run.id,
                tenant_id=run.tenant_id,
                app_id=run.app_id,
                reviewer_user_id=review.reviewer_user_id,
                review_status=review.status,
                overall_decision=review.overall_decision,
                reviewed_at=review.completed_at or review.updated_at,
                # Strip the review item_key's "<type>:" prefix (e.g. "adversarial:108",
                # "thread:thrd-…") so it joins the spine's bare target_key.
                target_key=item.item_key.split(":", 1)[1] if ":" in item.item_key else item.item_key,
                target_type=item.item_type,
                key=item.attribute_key,
                decision=item.decision,
                original_value=item.original_value,
                reviewed_value=item.reviewed_value,
                reason_code=item.reason_code,
                note=item.note,
            ))
            count += 1
        await self.db.flush()
        return count

    async def _populate_lead_signals(self, run: EvaluationRun) -> int:
        """Preserved CRM-leg signal write: delete-then-insert ``analytics.fact_lead_signal``
        for this run via the ``llm_transcript`` strategy. Only call-quality runs carry signals."""
        await self.db.execute(delete(FactLeadSignal).where(FactLeadSignal.eval_run_id == run.id))
        if run.eval_type != "call_quality":
            await self.db.flush()
            return 0
        thread_children = list((await self.db.execute(
            select(EvaluationRunThreadResult).where(EvaluationRunThreadResult.run_id == run.id)
        )).scalars().all())
        definition = await resolve_effective_definition(
            self.db, tenant_id=run.tenant_id, app_id=run.app_id, strategy="llm_transcript"
        )
        if definition is None:
            await self.db.flush()
            return 0
        strategy = get_strategy(definition.strategy)
        ctx = StrategyContext(tenant_id=run.tenant_id, app_id=run.app_id, eval_run=run)
        derived = await strategy.derive(
            definition=definition.definition, source_rows=thread_children, ctx=ctx
        )
        for signal in derived:
            row = derived_signal_to_fact_row(
                signal, tenant_id=run.tenant_id, app_id=run.app_id, signal_definition_id=definition.id
            )
            self.db.add(FactLeadSignal(**row))
        await self.db.flush()
        return len(derived)

    async def _delete_existing(self, run_id: UUID) -> int:
        total = 0
        for model in (FactEvaluation, FactEvaluationReview):
            result = await self.db.execute(delete(model).where(model.run_id == run_id))
            total += result.rowcount
        await self.db.flush()
        return total

    async def _refresh_rollup(self) -> None:
        """Rebuild the per-run rollup matview from the leaf fact. The one writer of the rollup."""
        await self.db.execute(text("REFRESH MATERIALIZED VIEW analytics.agg_evaluation_run"))
