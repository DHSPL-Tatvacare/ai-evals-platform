"""The ONE writer for the unified evaluation spine: Run → Target → Evaluation → Detail."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eval_run import EvaluationRun
from app.models.evaluation import Evaluation, EvaluationDetail, EvaluationTarget
from app.services.evaluators.output_atoms import EvaluationDraft, EvaluatorRef

logger = logging.getLogger(__name__)


def _evaluator_key(evaluator_id, evaluator_ref: dict | None) -> tuple:
    """Identity used to make re-runs idempotent (evaluator on a target)."""
    if evaluator_id is not None:
        return ("id", str(evaluator_id))
    return ("name", (evaluator_ref or {}).get("name"))


async def _resolve_target(db: AsyncSession, run: EvaluationRun, draft: EvaluationDraft) -> EvaluationTarget:
    existing = (await db.execute(
        select(EvaluationTarget).where(
            EvaluationTarget.run_id == run.id,
            EvaluationTarget.target_key == draft.target.key,
            EvaluationTarget.tenant_id == run.tenant_id,
        )
    )).scalars().first()
    if existing is not None:
        # Refresh subject metadata so re-runs/backfills pick up newly-carried attributes.
        existing.target_type = draft.target.type
        existing.source_ref = draft.target.source_ref
        existing.attributes = draft.target.attributes
        return existing
    target = EvaluationTarget(
        run_id=run.id,
        tenant_id=run.tenant_id,
        user_id=run.user_id,
        app_id=run.app_id,
        target_key=draft.target.key,
        target_type=draft.target.type,
        source_ref=draft.target.source_ref,
        attributes=draft.target.attributes,
    )
    db.add(target)
    await db.flush()
    return target


async def persist_evaluation(
    db: AsyncSession, run: EvaluationRun, drafts: list[EvaluationDraft]
) -> list[Evaluation]:
    """Write drafts onto the spine. Idempotent per (run, target_key, evaluator)."""
    persisted: list[Evaluation] = []
    for draft in drafts:
        target = await _resolve_target(db, run, draft)
        evaluator: EvaluatorRef = draft.evaluator
        ref_payload = evaluator.as_payload()
        new_key = _evaluator_key(evaluator.id, ref_payload)

        existing_evals = (await db.execute(
            select(Evaluation).where(Evaluation.target_id == target.id)
        )).scalars().all()
        for ev in existing_evals:
            if _evaluator_key(ev.evaluator_id, ev.evaluator_ref) == new_key:
                await db.delete(ev)  # DB FK CASCADE removes its details
        await db.flush()

        headline = draft.headline
        evaluation = Evaluation(
            run_id=run.id,
            target_id=target.id,
            tenant_id=run.tenant_id,
            app_id=run.app_id,
            evaluator_id=evaluator.id,
            evaluator_ref=ref_payload,
            status=draft.status,
            headline_key=headline.key if headline else None,
            headline_score=headline.score if headline else None,
            headline_max=headline.max if headline else None,
            verdict=headline.verdict if headline else None,
            reasoning=headline.reasoning if headline else None,
            raw_payload=draft.raw_payload,
        )
        db.add(evaluation)
        await db.flush()

        for atom in draft.details:
            db.add(EvaluationDetail(
                evaluation_id=evaluation.id,
                run_id=run.id,
                tenant_id=run.tenant_id,
                app_id=run.app_id,
                style=atom.style,
                key=atom.key,
                label=atom.label,
                score=atom.score,
                max=atom.max,
                status=atom.status,
                severity=atom.severity,
                locator=atom.locator,
                is_main=atom.is_main,
                weight=atom.weight,
                reference_text=atom.reference_text,
                candidate_text=atom.candidate_text,
                explanation=atom.explanation,
            ))
        await db.flush()
        persisted.append(evaluation)
    return persisted


async def safe_persist(db: AsyncSession, run_ctx, drafts: list[EvaluationDraft]) -> None:
    """Additive dual-write helper: persist + commit, swallowing failures so the legacy path is never broken."""
    if not drafts:
        return
    try:
        await persist_evaluation(db, run_ctx, drafts)
        await db.commit()
    except Exception:
        logger.warning("evaluation spine dual-write failed for run %s", getattr(run_ctx, "id", None), exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
