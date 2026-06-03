"""Reconstruct report source-data + run-level summary from the unified evaluation spine.

Reports read structured findings from ``platform.evaluation_{targets,evaluations}`` and raw
evidence from ``evaluation.raw_payload`` — never the legacy ``result``/``summary``/``thread_results``
columns. Per-eval_type summary reconstruction is the only eval_type-aware code (documented
exception, mirrors the backfill parsers): each eval_type's runner derived a different run-level
rollup, so each rollup the report reads is rebuilt from the spine here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eval_run import EvaluationRun
from app.models.evaluation import Evaluation, EvaluationDetail, EvaluationTarget


@dataclass
class ThreadEvidence:
    """Spine-backed stand-in for a legacy ``EvaluationRunThreadResult`` row."""
    thread_id: str
    result: dict
    intent_accuracy: float | None = None
    worst_correctness: str | None = None
    efficiency_verdict: str | None = None
    success_status: bool = False


@dataclass
class AdversarialEvidence:
    """Spine-backed stand-in for a legacy ``EvaluationRunAdversarialResult`` row."""
    id: str
    result: dict
    verdict: str | None = None
    goal_achieved: bool = False
    goal_flow: list = field(default_factory=list)
    active_traits: list = field(default_factory=list)
    total_turns: int = 0
    difficulty: str | None = None


def _f(value) -> float | None:
    return float(value) if value is not None else None


async def _grouped_targets(
    db: AsyncSession, run_id: UUID, *, target_types: tuple[str, ...] | None = None, exclude: tuple[str, ...] = (),
) -> list[tuple[EvaluationTarget, list[Evaluation]]]:
    """Targets for a run, each with its evaluations, ordered by insertion order.

    ``MIN(evaluation_details.id)`` (a bigint sequence written target-by-target) reproduces the
    legacy ``thread_results``/``adversarial_results`` row order, so report tie-breaks (equal-rate
    rules, equal-score exemplars) match; for live runs it is simply evaluation order.
    """
    query = (
        select(EvaluationTarget, Evaluation)
        .join(Evaluation, Evaluation.target_id == EvaluationTarget.id)
        .where(EvaluationTarget.run_id == run_id)
    )
    if target_types is not None:
        query = query.where(EvaluationTarget.target_type.in_(target_types))
    if exclude:
        query = query.where(EvaluationTarget.target_type.notin_(exclude))
    rows = (await db.execute(query)).all()

    ord_rows = (await db.execute(
        select(Evaluation.target_id, func.min(EvaluationDetail.id))
        .join(EvaluationDetail, EvaluationDetail.evaluation_id == Evaluation.id)
        .where(Evaluation.run_id == run_id)
        .group_by(Evaluation.target_id)
    )).all()
    ord_map = {tid: o for tid, o in ord_rows}

    grouped: dict[UUID, tuple[EvaluationTarget, list[Evaluation]]] = {}
    for target, ev in rows:
        if target.id not in grouped:
            grouped[target.id] = (target, [])
        grouped[target.id][1].append(ev)

    ordered = list(grouped.values())
    ordered.sort(key=lambda item: (ord_map.get(item[0].id) is None, ord_map.get(item[0].id) or 0, str(item[0].id)))
    return ordered


async def load_thread_evidence(db: AsyncSession, run_id: UUID) -> list[ThreadEvidence]:
    """One ThreadEvidence per target. The per-target evaluators share one full ``result``
    in ``raw_payload``; the legacy verdict columns map to the named evaluators' headlines."""
    out: list[ThreadEvidence] = []
    for target, evals in await _grouped_targets(db, run_id, exclude=("test_case",)):
        by_name = {(e.evaluator_ref or {}).get("name"): e for e in evals}
        result = next((e.raw_payload for e in evals if e.raw_payload), None) or {}
        success = result.get("success_status")
        if success is None:
            success = any(e.status == "ok" for e in evals)
        intent = by_name.get("intent")
        correctness = by_name.get("correctness")
        efficiency = by_name.get("efficiency")
        out.append(ThreadEvidence(
            thread_id=target.target_key,
            result=result,
            intent_accuracy=_f(intent.headline_score) if intent else None,
            worst_correctness=correctness.verdict if correctness else None,
            efficiency_verdict=efficiency.verdict if efficiency else None,
            success_status=bool(success),
        ))
    return out


async def load_adversarial_evidence(db: AsyncSession, run_id: UUID) -> list[AdversarialEvidence]:
    """One AdversarialEvidence per test-case target. Subject dims come from ``target.attributes``;
    verdict/goal from the single evaluator's headline; the conversation from ``raw_payload``."""
    out: list[AdversarialEvidence] = []
    for target, evals in await _grouped_targets(db, run_id, target_types=("test_case",)):
        ev = evals[0]
        attrs = target.attributes if isinstance(target.attributes, dict) else {}
        result = ev.raw_payload or {}
        out.append(AdversarialEvidence(
            id=target.target_key,
            result=result,
            verdict=ev.verdict,
            goal_achieved=bool(ev.headline_score) if ev.headline_score is not None else False,
            goal_flow=attrs.get("goal_flow") or [],
            active_traits=attrs.get("active_traits") or [],
            total_turns=int(attrs.get("total_turns") or 0),
            difficulty=attrs.get("difficulty"),
        ))
    return out


def reconstruct_thread_summary(threads: list[ThreadEvidence]) -> dict:
    """Rebuild the chat-thread run rollup the report reads (verdict distributions + intent mean)."""
    correctness: dict[str, int] = {}
    efficiency: dict[str, int] = {}
    intents: list[float] = []
    custom: dict[str, dict] = {}
    for t in threads:
        if t.worst_correctness:
            correctness[t.worst_correctness] = correctness.get(t.worst_correctness, 0) + 1
        if t.efficiency_verdict:
            efficiency[t.efficiency_verdict] = efficiency.get(t.efficiency_verdict, 0) + 1
        if t.intent_accuracy is not None:
            intents.append(t.intent_accuracy)
        for eid in (t.result.get("custom_evaluations") or {}):
            custom.setdefault(str(eid), {})
    summary: dict = {"total_threads": len(threads), "completed": len(threads), "errors": 0}
    if intents:
        summary["avg_intent_accuracy"] = round(sum(intents) / len(intents), 4)
    if correctness:
        summary["correctness_verdicts"] = correctness
    if efficiency:
        summary["efficiency_verdicts"] = efficiency
    if custom:
        summary["custom_evaluations"] = custom
    return summary


def reconstruct_adversarial_summary(adversarial: list[AdversarialEvidence]) -> dict:
    """Rebuild the adversarial run rollup the report reads (total + infra-error count)."""
    from app.services.evaluators.adversarial_canonical import build_canonical_adversarial_case

    errors = 0
    for ae in adversarial:
        case = build_canonical_adversarial_case(
            ae.result or {}, row_verdict=ae.verdict, row_goal_achieved=ae.goal_achieved,
            row_goal_flow=ae.goal_flow, row_active_traits=ae.active_traits, row_total_turns=ae.total_turns,
        )
        if case.get("derived", {}).get("isInfraFailure"):
            errors += 1
    return {"total_tests": len(adversarial), "errors": errors}


async def load_transcript_payload(db: AsyncSession, run: EvaluationRun) -> tuple[dict, dict]:
    """Reconstruct ``(result, summary)`` for a transcript-app run (full_evaluation / custom).

    The single evaluation's ``raw_payload`` IS the legacy ``run.result``. The legacy ``run.summary``
    is the runner's derived rollup, rebuilt here from that payload — via the transcript runner's own
    ``_build_summary`` for full_evaluation, or the evaluation headline for a custom rubric.
    """
    grouped = await _grouped_targets(db, run.id)
    if not grouped:
        return {}, {}
    _, evals = grouped[0]
    ev = evals[0]
    result = ev.raw_payload or {}
    if run.eval_type == "custom":
        summary: dict = {}
        if ev.headline_score is not None:
            summary["overall_score"] = _f(ev.headline_score)
        if ev.headline_max is not None:
            summary["max_score"] = _f(ev.headline_max)
        if ev.reasoning:
            summary["reasoning"] = ev.reasoning
        return result, summary
    return result, _build_transcript_summary(result)


def _build_transcript_summary(result: dict) -> dict:
    from app.services.evaluators.flow_config import FlowConfig
    from app.services.evaluators.transcript_eval_runner import _build_summary

    flow_type = "api" if (result.get("flowType") or result.get("flow_type")) == "api" else "upload"
    return _build_summary(FlowConfig(flow_type=flow_type), result) or {}
