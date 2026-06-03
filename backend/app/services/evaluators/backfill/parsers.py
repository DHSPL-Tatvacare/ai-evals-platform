"""Backfill parsers: OLD stored JSON → EvaluationDrafts, dispatched by eval_type.

These are the ONLY app-aware code in this leg (documented exception): each eval_type stores a
different legacy JSON shape, so one parser per eval_type maps it onto the unified spine atoms.
eval_type strings are generic (no app names). Pure functions — no DB, unit-tested against verbatim
fixtures of the real stored JSON.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.services.evaluators.output_atoms import (
    DetailAtom,
    EvaluationDraft,
    EvaluatorRef,
    Headline,
    TargetRef,
)

_RULE_STATUS = {"FOLLOWED": "PASS", "VIOLATED": "FAIL", "NOT_APPLICABLE": "NA", "NOT_EVALUATED": "NA"}
_CORRECTNESS_RANK = {"PASS": 0, "SOFT FAIL": 1, "HARD FAIL": 2, "CRITICAL": 3}


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, AttributeError, TypeError):
        return None


def _rule_status(rc: dict) -> str:
    raw = (rc.get("status") or "").upper()
    if raw in _RULE_STATUS:
        return _RULE_STATUS[raw]
    followed = rc.get("followed")
    if followed is True:
        return "PASS"
    if followed is False:
        return "FAIL"
    return "NA"


def _rule_atoms(rule_compliance: Any) -> list[DetailAtom]:
    atoms: list[DetailAtom] = []
    for rc in rule_compliance or []:
        atoms.append(DetailAtom(
            style="rule",
            key=str(rc.get("rule_id") or "rule"),
            label=rc.get("section"),
            status=_rule_status(rc),
            explanation=rc.get("evidence") or None,
        ))
    return atoms


def _worst(verdicts: list[Any]) -> str | None:
    ranked = [(v, _CORRECTNESS_RANK.get(str(v).upper(), -1)) for v in verdicts if v]
    ranked = [(v, r) for v, r in ranked if r >= 0]
    return max(ranked, key=lambda x: x[1])[0] if ranked else None


def _severity(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).lower()
    return s if s in ("minor", "moderate", "critical") else None


def parse_batch_thread(thread_id: str, result: dict) -> list[EvaluationDraft]:
    """kaira chat-thread → correctness/efficiency (rule) + intent (dimension)."""
    target = TargetRef(key=str(thread_id), type="chat_thread")
    drafts: list[EvaluationDraft] = []

    corr = result.get("correctness_evaluations") or []
    if corr:
        atoms: list[DetailAtom] = []
        for ce in corr:
            atoms.extend(_rule_atoms(ce.get("rule_compliance")))
        drafts.append(EvaluationDraft(
            target=target, evaluator=EvaluatorRef(name="correctness"), status="ok",
            headline=Headline(key="worst_correctness", verdict=_worst([ce.get("verdict") for ce in corr])),
            details=atoms, raw_payload=result,
        ))

    eff = result.get("efficiency_evaluation")
    if isinstance(eff, dict):
        drafts.append(EvaluationDraft(
            target=target, evaluator=EvaluatorRef(name="efficiency"), status="ok",
            headline=Headline(key="efficiency_verdict", verdict=eff.get("verdict")),
            details=_rule_atoms(eff.get("rule_compliance")), raw_payload=result,
        ))

    intents = result.get("intent_evaluations") or []
    if intents:
        total = len(intents)
        correct = sum(1 for ie in intents if ie.get("is_correct_intent"))
        acc = (correct / total) if total else None
        drafts.append(EvaluationDraft(
            target=target, evaluator=EvaluatorRef(name="intent"), status="ok",
            headline=Headline(key="intent_accuracy", score=acc, max=1.0),
            details=[DetailAtom(style="dimension", key="intent_accuracy", label="Intent Accuracy",
                                score=acc, max=1.0, is_main=True)],
            raw_payload=result,
        ))

    return drafts


def parse_call_quality(thread_id: str, result: dict) -> list[EvaluationDraft]:
    """inside-sales call → one evaluation per rubric; output.reasoning[] → dimension atoms."""
    cm = result.get("call_metadata") or {}
    _agent = (cm.get("rep_label") or cm.get("agent") or "").strip() or None
    target = TargetRef(key=str(thread_id), type="chat_thread", attributes={
        "agent": _agent,
        "rep_label": _agent,  # FE call-quality row reads rep_label for the Agent column
        "lead_id": cm.get("prospect_id") or cm.get("lead"),
        "direction": cm.get("direction"),
        "duration_seconds": cm.get("duration") or cm.get("duration_seconds"),
    })
    drafts: list[EvaluationDraft] = []
    for ev in result.get("evaluations") or []:
        output = ev.get("output") or {}
        atoms: list[DetailAtom] = []
        for r in output.get("reasoning") or []:
            dim = r.get("dimension")
            atoms.append(DetailAtom(
                style="dimension", key=str(dim or "dimension"), label=dim,
                score=r.get("score"), max=r.get("max"), explanation=r.get("explanation"),
            ))
        overall = output.get("overall_score")
        if overall is not None:
            atoms.append(DetailAtom(style="dimension", key="overall_score", label="Overall Score",
                                    score=overall, is_main=True))
        if not atoms:
            continue
        drafts.append(EvaluationDraft(
            target=target,
            evaluator=EvaluatorRef(id=_as_uuid(ev.get("evaluator_id")), name=ev.get("evaluator_name")),
            status="ok",
            headline=Headline(key="overall_score", score=overall) if overall is not None else None,
            details=atoms, raw_payload=result,
        ))
    return drafts


def parse_batch_adversarial(case_id: str, result: dict) -> list[EvaluationDraft]:
    """kaira adversarial test case → rule atoms + goal verdict headline."""
    tc = result.get("test_case") or {}
    goal_achieved = result.get("goal_achieved")
    return [EvaluationDraft(
        target=TargetRef(
            key=str(case_id), type="test_case",
            attributes={
                "difficulty": tc.get("difficulty"),
                "goal_flow": tc.get("goal_flow"),
                "active_traits": tc.get("active_traits"),
                "persona_labels": tc.get("persona_labels"),
            },
        ),
        evaluator=EvaluatorRef(name="adversarial"), status="ok",
        headline=Headline(
            key="goal_achieved", verdict=result.get("verdict"),
            score=(1.0 if goal_achieved else 0.0) if goal_achieved is not None else None, max=1.0,
            reasoning=result.get("reasoning"),
        ),
        details=_rule_atoms(result.get("rule_compliance")),
        raw_payload=result,
    )]


def parse_full_evaluation(target_key: str, result: dict, summary: dict | None) -> list[EvaluationDraft]:
    """voice-rx transcript critique → comparison atoms (segments + field critiques)."""
    critique = result.get("critique") or {}
    atoms: list[DetailAtom] = []
    for idx, seg in enumerate(critique.get("segments") or []):
        atoms.append(DetailAtom(
            style="comparison", key=str(seg.get("category") or f"segment_{idx}"), label=seg.get("category"),
            locator=f"segment:{seg.get('segmentIndex', idx)}", severity=_severity(seg.get("severity")),
            reference_text=seg.get("originalText"), candidate_text=seg.get("judgeText"),
            explanation=seg.get("discrepancy"),
        ))
    for idx, fc in enumerate(critique.get("fieldCritiques") or []):
        key = fc.get("fieldPath") or fc.get("fieldName") or f"field_{idx}"
        api_value = fc.get("apiValue")
        atoms.append(DetailAtom(
            style="comparison", key=str(key), label=fc.get("fieldPath") or fc.get("fieldName"),
            locator=f"api_field:{key}", severity=_severity(fc.get("severity")),
            reference_text=fc.get("judgeValue"), candidate_text=None if api_value is None else str(api_value),
            explanation=fc.get("critique"),
        ))
    overall = (summary or {}).get("overall_accuracy")
    if not atoms and overall is None:
        return []
    return [EvaluationDraft(
        target=TargetRef(key=str(target_key), type="transcript"),
        evaluator=EvaluatorRef(name="correctness"), status="ok",
        headline=Headline(key="overall_accuracy", score=overall, max=1.0) if overall is not None else None,
        details=atoms,
        raw_payload=result,
    )]


def parse_custom(target_key: str, result: dict, summary: dict | None) -> list[EvaluationDraft]:
    """voice-rx custom correctness → output.errors[] → comparison atoms; summary → headline."""
    output = result.get("output") or {}
    atoms: list[DetailAtom] = []
    for idx, err in enumerate(output.get("errors") or []):
        entity = err.get("entity")
        atoms.append(DetailAtom(
            style="comparison", key=str(entity or f"error_{idx}"), label=entity,
            locator=f"entity:{entity}" if entity else None,
            reference_text=err.get("source_says"), candidate_text=err.get("output_says"),
        ))
    summary = summary or {}
    overall = summary.get("overall_score")
    if not atoms and overall is None:
        return []
    meta = summary.get("metadata") or {}
    headline = None
    if overall is not None:
        headline = Headline(
            key=meta.get("main_metric_key") or "overall_score", score=overall,
            max=summary.get("max_score"), reasoning=summary.get("reasoning"),
        )
    return [EvaluationDraft(
        target=TargetRef(key=str(target_key), type="transcript"),
        evaluator=EvaluatorRef(name="correctness"), status="ok",
        headline=headline, details=atoms,
        raw_payload=result,
    )]


def build_drafts(run, thread_results, adversarial_results) -> list[EvaluationDraft]:
    """Dispatch a run's legacy rows to the eval_type parser → drafts for persist_evaluation."""
    et = run.eval_type
    if et == "batch_thread":
        return [d for tr in thread_results for d in parse_batch_thread(tr.thread_id, tr.result or {})]
    if et == "call_quality":
        return [d for tr in thread_results for d in parse_call_quality(tr.thread_id, tr.result or {})]
    if et == "batch_adversarial":
        return [d for ar in adversarial_results for d in parse_batch_adversarial(str(ar.id), ar.result or {})]
    if et == "full_evaluation":
        return parse_full_evaluation(str(run.id), run.result or {}, run.summary)
    if et == "custom":
        return parse_custom(str(run.id), run.result or {}, run.summary)
    return []
