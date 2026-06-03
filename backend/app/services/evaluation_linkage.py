"""Evaluation-linkage helpers consumed by the inside-sales listing surfaces.

These functions overlay the latest eval result onto a call DTO and project
eval history. They are read-only against the unified evaluation spine
(``platform.evaluation_targets`` → ``evaluations`` → ``evaluation_details``,
joined to ``platform.evaluation_runs`` for scope/status); the eval runner
itself does not import this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.eval_run import EvaluationRun
from app.models.evaluation import Evaluation, EvaluationDetail, EvaluationTarget

VISIBLE_EVAL_STATUSES = ("completed", "completed_with_errors")


@dataclass(frozen=True)
class EvalOverlay:
    eval_count: int
    latest_score: float | None
    latest_result: dict[str, Any] | None
    latest_run_id: str | None = None


def extract_eval_score(result: dict[str, Any] | None) -> float | None:
    raw = result or {}
    evaluations = raw.get("evaluations") or []
    if evaluations:
        output = evaluations[0].get("output") or {}
        score = output.get("overall_score")
        if score is not None:
            return score
    return (raw.get("output") or {}).get("overall_score")


def _detail_to_atom(detail: EvaluationDetail) -> dict[str, Any]:
    """Project one spine detail into a structured atom mirroring the FE contract."""
    return {
        "style": detail.style,
        "key": detail.key,
        "label": detail.label,
        "score": float(detail.score) if detail.score is not None else None,
        "max": float(detail.max) if detail.max is not None else None,
        "status": detail.status,
        "severity": detail.severity,
        "locator": detail.locator,
        "isMain": detail.is_main,
        "referenceText": detail.reference_text,
        "candidateText": detail.candidate_text,
        "explanation": detail.explanation,
    }


def _evaluation_to_result(evaluation: Evaluation) -> dict[str, Any]:
    """Reconstruct the legacy ``result`` dict shape from a spine ``Evaluation``.

    The overlay/history consumers (``extract_eval_score`` + the FE) read
    ``output.overall_score`` and an ``evaluations[]`` list; rebuild that from
    the headline + details so the read surface is unchanged after the flip."""
    score = (
        float(evaluation.headline_score)
        if evaluation.headline_score is not None
        else None
    )
    output: dict[str, Any] = {"overall_score": score}
    details = [_detail_to_atom(detail) for detail in evaluation.details]
    return {
        "output": output,
        "verdict": evaluation.verdict,
        "reasoning": evaluation.reasoning,
        "evaluations": [{"output": output}],
        "details": details,
    }


async def fetch_latest_eval_overlays(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    app_id: str,
    thread_ids: Sequence[str],
    statuses: Sequence[str] = VISIBLE_EVAL_STATUSES,
) -> dict[str, EvalOverlay]:
    clean_thread_ids = tuple(thread_id for thread_id in thread_ids if thread_id)
    if not clean_thread_ids:
        return {}

    # Per target_key: total evaluation count + the id of the most-recent
    # evaluation (latest run, then latest evaluation within the run).
    base_join = (
        select(
            EvaluationTarget.target_key.label("target_key"),
            Evaluation.id.label("evaluation_id"),
            EvaluationRun.completed_at.label("run_completed_at"),
            EvaluationRun.created_at.label("run_created_at"),
            Evaluation.created_at.label("eval_created_at"),
        )
        .join(EvaluationTarget, Evaluation.target_id == EvaluationTarget.id)
        .join(EvaluationRun, Evaluation.run_id == EvaluationRun.id)
        .where(
            EvaluationTarget.target_key.in_(clean_thread_ids),
            EvaluationTarget.tenant_id == tenant_id,
            EvaluationTarget.user_id == user_id,
            EvaluationTarget.app_id == app_id,
            EvaluationRun.status.in_(tuple(statuses)),
        )
        .subquery()
    )

    ranked = select(
        base_join.c.target_key,
        base_join.c.evaluation_id,
        func.row_number()
        .over(
            partition_by=base_join.c.target_key,
            order_by=(
                base_join.c.run_completed_at.desc().nullslast(),
                base_join.c.run_created_at.desc().nullslast(),
                base_join.c.eval_created_at.desc().nullslast(),
            ),
        )
        .label("rn"),
        func.count()
        .over(partition_by=base_join.c.target_key)
        .label("eval_count"),
    ).subquery()

    latest = await db.execute(
        select(ranked.c.target_key, ranked.c.evaluation_id, ranked.c.eval_count).where(
            ranked.c.rn == 1
        )
    )
    rows = latest.all()
    if not rows:
        return {}

    eval_ids = [evaluation_id for _, evaluation_id, _ in rows]
    eval_records = await db.execute(
        select(Evaluation)
        .where(Evaluation.id.in_(eval_ids))
        .options(selectinload(Evaluation.details))
    )
    eval_by_id = {ev.id: ev for ev in eval_records.scalars().all()}

    overlays: dict[str, EvalOverlay] = {}
    for target_key, evaluation_id, eval_count in rows:
        evaluation = eval_by_id.get(evaluation_id)
        if evaluation is None:
            continue
        result = _evaluation_to_result(evaluation)
        overlays[str(target_key)] = EvalOverlay(
            eval_count=int(eval_count or 0),
            latest_score=extract_eval_score(result),
            latest_result=result,
            latest_run_id=str(evaluation.run_id),
        )
    return overlays


async def list_eval_history_entries(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    app_id: str,
    thread_ids: Sequence[str],
    statuses: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    clean_thread_ids = tuple(thread_id for thread_id in thread_ids if thread_id)
    if not clean_thread_ids:
        return []

    statement = (
        select(Evaluation, EvaluationTarget.target_key)
        .join(EvaluationTarget, Evaluation.target_id == EvaluationTarget.id)
        .join(EvaluationRun, Evaluation.run_id == EvaluationRun.id)
        .where(
            EvaluationTarget.target_key.in_(clean_thread_ids),
            EvaluationTarget.tenant_id == tenant_id,
            EvaluationTarget.user_id == user_id,
            EvaluationTarget.app_id == app_id,
        )
        .options(selectinload(Evaluation.details))
        .order_by(Evaluation.created_at.desc())
    )
    if statuses:
        statement = statement.where(EvaluationRun.status.in_(tuple(statuses)))

    result = await db.execute(statement)
    return [
        {
            "id": str(evaluation.id),
            "thread_id": target_key,
            "run_id": str(evaluation.run_id),
            "result": _evaluation_to_result(evaluation),
            "created_at": _format_eval_history_timestamp(evaluation.created_at),
        }
        for evaluation, target_key in result.all()
    ]


def _format_eval_history_timestamp(value: datetime | None) -> str:
    return str(value) if value is not None else ""
