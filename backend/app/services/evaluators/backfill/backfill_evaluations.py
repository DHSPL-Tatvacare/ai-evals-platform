"""Backfill the unified evaluation spine from legacy JSON. READ-ONLY on old tables; idempotent.

Iterates evaluation_runs, reads their legacy child rows (thread/adversarial results) read-only,
maps them via the per-eval_type parsers, and writes the spine via the single persist_evaluation
writer. Re-runs insert net-zero (persist_evaluation deletes-then-inserts per evaluator on a target).
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eval_run import EvaluationRun, EvaluationRunAdversarialResult, EvaluationRunThreadResult
from app.services.evaluators.backfill.parsers import build_drafts
from app.services.evaluators.persistence import persist_evaluation

logger = logging.getLogger(__name__)


async def backfill_run(db: AsyncSession, run: EvaluationRun) -> dict:
    """Backfill one run. Children loaded with filtered selects (no db.get on owned data)."""
    thread_results = (await db.execute(
        select(EvaluationRunThreadResult).where(EvaluationRunThreadResult.run_id == run.id)
    )).scalars().all()
    adversarial_results = (await db.execute(
        select(EvaluationRunAdversarialResult).where(EvaluationRunAdversarialResult.run_id == run.id)
    )).scalars().all()

    drafts = build_drafts(run, thread_results, adversarial_results)
    evaluations = await persist_evaluation(db, run, drafts)
    return {
        "run_id": str(run.id),
        "eval_type": run.eval_type,
        "targets": len({d.target.key for d in drafts}),
        "evaluations": len(evaluations),
    }


async def backfill_evaluations(
    db: AsyncSession,
    *,
    run_ids: list[uuid.UUID] | None = None,
    app_id: str | None = None,
    tenant_id: uuid.UUID | None = None,
) -> dict:
    """Backfill many runs. Written rows inherit each source run's tenant/app/user.

    This is a platform-wide one-time data migration, so the scan is NOT auto-scoped to the
    submitter's tenant; pass ``tenant_id``/``app_id`` to restrict it explicitly.
    """
    query = select(EvaluationRun)
    if run_ids:
        query = query.where(EvaluationRun.id.in_(run_ids))
    if app_id:
        query = query.where(EvaluationRun.app_id == app_id)
    if tenant_id:
        query = query.where(EvaluationRun.tenant_id == tenant_id)
    runs = (await db.execute(query)).scalars().all()

    totals = {"runs": 0, "targets": 0, "evaluations": 0, "errors": 0}
    for run in runs:
        try:
            summary = await backfill_run(db, run)
            await db.commit()
        except Exception:
            logger.warning("backfill failed for run %s", run.id, exc_info=True)
            await db.rollback()
            totals["errors"] += 1
            continue
        totals["runs"] += 1
        totals["targets"] += summary["targets"]
        totals["evaluations"] += summary["evaluations"]
    return totals
