"""Map each runner's freshly-computed evaluator output → EvaluationDrafts (spine write contract).

Each builder operates on the runner's own output shape (runner-local knowledge, not app_id
branching). They are pure functions so they unit-test without a DB.
"""
from __future__ import annotations

from typing import Any

from app.services.evaluators.output_atoms import (
    DetailAtom,
    EvaluationDraft,
    EvaluatorRef,
    Headline,
    TargetRef,
)

# RuleCompliance.status vocabulary → DetailAtom status vocabulary (PASS|FAIL|NA)
_RULE_STATUS = {"FOLLOWED": "PASS", "VIOLATED": "FAIL", "NOT_APPLICABLE": "NA", "NOT_EVALUATED": "NA"}
# correctness verdict severity ranking (worst wins for the headline)
_CORRECTNESS_RANK = {"PASS": 0, "SOFT FAIL": 1, "HARD FAIL": 2, "CRITICAL": 3}


def _rule_status(rc: Any) -> str:
    raw = (getattr(rc, "status", None) or "").upper()
    if raw in _RULE_STATUS:
        return _RULE_STATUS[raw]
    followed = getattr(rc, "followed", None)
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
            key=str(getattr(rc, "rule_id", None) or "rule"),
            label=getattr(rc, "section", None),
            status=_rule_status(rc),
            explanation=getattr(rc, "evidence", None) or None,
        ))
    return atoms


def _worst_correctness(verdicts: list[str | None]) -> str | None:
    ranked = [(v, _CORRECTNESS_RANK.get(str(v).upper(), -1)) for v in verdicts if v]
    ranked = [(v, r) for v, r in ranked if r >= 0]
    return max(ranked, key=lambda x: x[1])[0] if ranked else None


def _severity(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).lower()
    return s if s in ("minor", "moderate", "critical") else None


def thread_drafts(
    *,
    thread_id: str,
    intent_results: list | None = None,
    correctness_results: list | None = None,
    efficiency_result: Any = None,
    raw_payload: dict | None = None,
) -> list[EvaluationDraft]:
    """Chat-thread target → one evaluation per evaluator (correctness/efficiency → rule, intent → dimension)."""
    target = TargetRef(key=str(thread_id), type="chat_thread")
    drafts: list[EvaluationDraft] = []

    if correctness_results:
        atoms: list[DetailAtom] = []
        for ce in correctness_results:
            atoms.extend(_rule_atoms(getattr(ce, "rule_compliance", None)))
        worst = _worst_correctness([getattr(ce, "verdict", None) for ce in correctness_results])
        drafts.append(EvaluationDraft(
            target=target, evaluator=EvaluatorRef(name="correctness"), status="ok",
            headline=Headline(key="worst_correctness", verdict=worst), details=atoms, raw_payload=raw_payload,
        ))

    if efficiency_result is not None:
        drafts.append(EvaluationDraft(
            target=target, evaluator=EvaluatorRef(name="efficiency"), status="ok",
            headline=Headline(key="efficiency_verdict", verdict=getattr(efficiency_result, "verdict", None)),
            details=_rule_atoms(getattr(efficiency_result, "rule_compliance", None)), raw_payload=raw_payload,
        ))

    if intent_results:
        total = len(intent_results)
        correct = sum(1 for ie in intent_results if getattr(ie, "is_correct_intent", False))
        acc = (correct / total) if total else None
        drafts.append(EvaluationDraft(
            target=target, evaluator=EvaluatorRef(name="intent"), status="ok",
            headline=Headline(key="intent_accuracy", score=acc, max=1.0),
            details=[DetailAtom(style="dimension", key="intent_accuracy", label="Intent Accuracy",
                                score=acc, max=1.0, is_main=True)],
            raw_payload=raw_payload,
        ))

    return drafts


def custom_drafts(
    *,
    target_key: str,
    target_type: str,
    output: dict | None,
    output_schema: list[dict] | None,
    scores: dict | None,
    evaluator_id=None,
    evaluator_name: str | None = None,
    raw_payload: dict | None = None,
) -> list[EvaluationDraft]:
    """Custom evaluator → one evaluation; numeric output_schema fields become dimension atoms."""
    output = output or {}
    meta = (scores or {}).get("metadata") or {}
    main_key = meta.get("main_metric_key")
    atoms: list[DetailAtom] = []
    for field in output_schema or []:
        if field.get("type") != "number":
            continue
        key = field.get("key")
        if key is None or output.get(key) is None:
            continue
        thresholds = field.get("thresholds") or {}
        atoms.append(DetailAtom(
            style="dimension", key=str(key), label=field.get("label") or str(key),
            score=output.get(key), max=thresholds.get("green"), is_main=(key == main_key),
        ))
    headline = None
    if scores:
        headline = Headline(
            key=main_key, score=scores.get("overall_score"),
            max=scores.get("max_score"), reasoning=scores.get("reasoning"),
        )
    return [EvaluationDraft(
        target=TargetRef(key=str(target_key), type=target_type),
        evaluator=EvaluatorRef(id=evaluator_id, name=evaluator_name),
        status="ok", headline=headline, details=atoms, raw_payload=raw_payload,
    )]


def transcript_drafts(
    *,
    target_key: str,
    evaluation: dict | None,
    summary: dict | None = None,
    raw_payload: dict | None = None,
) -> list[EvaluationDraft]:
    """Transcript target → one evaluation; critique discrepancies become comparison atoms."""
    critique = (evaluation or {}).get("critique") or {}
    atoms: list[DetailAtom] = []
    for idx, seg in enumerate(critique.get("segments") or []):
        atoms.append(DetailAtom(
            style="comparison",
            key=str(seg.get("category") or f"segment_{idx}"),
            label=seg.get("category"),
            locator=f"segment:{seg.get('segmentIndex', idx)}",
            severity=_severity(seg.get("severity")),
            reference_text=seg.get("originalText") or seg.get("source_says"),
            candidate_text=seg.get("judgeText") or seg.get("output_says"),
            explanation=seg.get("discrepancy") or seg.get("reasoning"),
        ))
    for idx, fc in enumerate(critique.get("fieldCritiques") or []):
        key = fc.get("fieldName") or fc.get("field") or f"field_{idx}"
        api_value = fc.get("apiValue")
        atoms.append(DetailAtom(
            style="comparison",
            key=str(key),
            label=fc.get("fieldName") or fc.get("field"),
            locator=f"api_field:{key}",
            severity=_severity(fc.get("severity")),
            reference_text=fc.get("expectedValue") or fc.get("expected") or fc.get("source_says"),
            candidate_text=None if api_value is None else str(api_value),
            explanation=fc.get("discrepancy") or fc.get("reasoning"),
        ))
    headline = None
    if summary and summary.get("overall_accuracy") is not None:
        headline = Headline(key="overall_accuracy", score=summary.get("overall_accuracy"), max=1.0)
    return [EvaluationDraft(
        target=TargetRef(key=str(target_key), type="transcript"),
        evaluator=EvaluatorRef(name="correctness"), status="ok",
        headline=headline, details=atoms, raw_payload=raw_payload,
    )]


def adversarial_drafts(
    *,
    case_label: str,
    evaluation: Any,
    difficulty: str | None = None,
    goal_flow: list | None = None,
    active_traits: list | None = None,
    raw_payload: dict | None = None,
) -> list[EvaluationDraft]:
    """Adversarial test-case target → one evaluation; rule_compliance becomes rule atoms."""
    goal_achieved = getattr(evaluation, "goal_achieved", None)
    return [EvaluationDraft(
        target=TargetRef(
            key=str(case_label), type="test_case",
            attributes={"difficulty": difficulty, "goal_flow": goal_flow, "active_traits": active_traits},
        ),
        evaluator=EvaluatorRef(name="adversarial"), status="ok",
        headline=Headline(
            key="goal_achieved", verdict=getattr(evaluation, "verdict", None),
            score=(1.0 if goal_achieved else 0.0) if goal_achieved is not None else None, max=1.0,
        ),
        details=_rule_atoms(getattr(evaluation, "rule_compliance", None)),
        raw_payload=raw_payload,
    )]
