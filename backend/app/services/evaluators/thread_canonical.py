"""Canonical thread-evaluation adapters for persistence, API, and analytics."""

from __future__ import annotations

import re
from typing import Any

from app.services.evaluators.models import normalize_rule_outcome

_RULE_STATUS_PRIORITY = {
    "VIOLATED": 0,
    "FOLLOWED": 1,
    "NOT_APPLICABLE": 2,
    "NOT_EVALUATED": 3,
}

_EFFICIENCY_VERDICTS = {
    "EFFICIENT",
    "ACCEPTABLE",
    "INCOMPLETE",
    "FRICTION",
    "BROKEN",
    "NOT_APPLICABLE",
}

_CORRECTNESS_VERDICTS = {
    "PASS",
    "SOFT_FAIL",
    "HARD_FAIL",
    "CRITICAL",
    "NOT_APPLICABLE",
}

def normalize_efficiency_verdict(raw_verdict: str | None) -> str | None:
    if not raw_verdict:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(raw_verdict)).strip("_").upper()
    return normalized if normalized in _EFFICIENCY_VERDICTS else None


def normalize_correctness_verdict(raw_verdict: str | None) -> str | None:
    if not raw_verdict:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(raw_verdict)).strip("_").upper()
    return normalized if normalized in _CORRECTNESS_VERDICTS else None


def _rule_source(
    *,
    source_type: str,
    source_label: str,
    rule_id: str,
    section: str,
    evidence: str,
    status: str,
    followed: bool | None,
) -> dict[str, Any]:
    return {
        "sourceType": source_type,
        "sourceLabel": source_label,
        "ruleId": rule_id,
        "section": section,
        "evidence": evidence,
        "status": status,
        "followed": followed,
    }


def _normalize_rule_outcomes(
    raw_rule_outcomes: list[dict[str, Any]] | None,
    *,
    source_type: str,
    source_label: str,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for item in raw_rule_outcomes or []:
        if not isinstance(item, dict):
            continue
        rule_id = item.get("rule_id") or item.get("ruleId")
        if not rule_id:
            continue
        status, followed = normalize_rule_outcome(item.get("status"), item.get("followed"))
        outcomes.append(
            _rule_source(
                source_type=source_type,
                source_label=source_label,
                rule_id=rule_id,
                section=item.get("section", ""),
                evidence=item.get("evidence", ""),
                status=status,
                followed=followed,
            )
        )
    return outcomes


def _aggregate_rule_outcomes(
    outcomes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome["ruleId"], []).append(outcome)

    aggregated: list[dict[str, Any]] = []
    summary = {
        "followed": 0,
        "violated": 0,
        "notApplicable": 0,
        "notEvaluated": 0,
        "evaluatedCount": 0,
    }

    for rule_id in sorted(grouped.keys()):
        sources = grouped[rule_id]
        winning = min(
            sources,
            key=lambda item: _RULE_STATUS_PRIORITY.get(item["status"], 99),
        )
        aggregated_item = {
            "ruleId": rule_id,
            "section": next((item.get("section", "") for item in sources if item.get("section")), ""),
            "status": winning["status"],
            "followed": winning["followed"],
            "evidence": winning.get("evidence", ""),
            "sources": sources,
        }
        aggregated.append(aggregated_item)

        if winning["status"] == "FOLLOWED":
            summary["followed"] += 1
            summary["evaluatedCount"] += 1
        elif winning["status"] == "VIOLATED":
            summary["violated"] += 1
            summary["evaluatedCount"] += 1
        elif winning["status"] == "NOT_APPLICABLE":
            summary["notApplicable"] += 1
        else:
            summary["notEvaluated"] += 1

    aggregated.sort(key=lambda item: (_RULE_STATUS_PRIORITY.get(item["status"], 99), item["ruleId"]))
    return aggregated, summary


def _normalize_thread_facts(result: dict[str, Any]) -> dict[str, Any]:
    thread = result.get("thread") or {}
    messages = list(thread.get("messages") or [])
    return {
        "threadId": thread.get("thread_id") or thread.get("threadId") or "",
        "userId": thread.get("user_id") or thread.get("userId") or "",
        "messageCount": thread.get("message_count") or thread.get("messageCount") or len(messages),
        "durationSeconds": thread.get("duration_seconds") or thread.get("durationSeconds") or 0,
        "hasImage": any(bool(message.get("has_image") or message.get("hasImage")) for message in messages),
    }


def _normalize_intent_block(result: dict[str, Any], *, row_intent_accuracy: float | None) -> dict[str, Any]:
    accuracy = result.get("intent_accuracy")
    if accuracy is None:
        accuracy = row_intent_accuracy
    return {
        "accuracy": accuracy,
        "evaluations": list(result.get("intent_evaluations") or []),
    }


def _normalize_efficiency_block(result: dict[str, Any], *, row_efficiency_verdict: str | None) -> dict[str, Any]:
    raw_efficiency = result.get("efficiency_evaluation") or {}
    verdict = normalize_efficiency_verdict(
        raw_efficiency.get("verdict") if isinstance(raw_efficiency, dict) else None
    )
    if verdict is None:
        verdict = normalize_efficiency_verdict(row_efficiency_verdict)
    return {
        "verdict": verdict,
        "taskCompleted": bool(raw_efficiency.get("task_completed")) if isinstance(raw_efficiency, dict) else False,
        "frictionTurns": list(raw_efficiency.get("friction_turns") or []) if isinstance(raw_efficiency, dict) else [],
        "recoveryQuality": raw_efficiency.get("recovery_quality") if isinstance(raw_efficiency, dict) else None,
        "failureReason": (
            raw_efficiency.get("failure_reason")
            or raw_efficiency.get("abandonment_reason")
            or ""
        ) if isinstance(raw_efficiency, dict) else "",
        "reasoning": raw_efficiency.get("reasoning", "") if isinstance(raw_efficiency, dict) else "",
        "ruleOutcomes": _normalize_rule_outcomes(
            raw_efficiency.get("rule_compliance") if isinstance(raw_efficiency, dict) else [],
            source_type="efficiency",
            source_label="Efficiency",
        ),
    }


def _normalize_correctness_block(
    result: dict[str, Any],
    *,
    row_worst_correctness: str | None,
) -> dict[str, Any]:
    normalized_evaluations: list[dict[str, Any]] = []
    raw_evaluations = list(result.get("correctness_evaluations") or [])

    for index, evaluation in enumerate(raw_evaluations):
        if not isinstance(evaluation, dict):
            continue
        normalized_evaluations.append(
            {
                "message": evaluation.get("message") or {},
                "verdict": normalize_correctness_verdict(evaluation.get("verdict")),
                "reasoning": evaluation.get("reasoning", ""),
                "hasImageContext": bool(evaluation.get("has_image_context") or evaluation.get("hasImageContext")),
                "calorieSanity": evaluation.get("calorie_sanity") or evaluation.get("calorieSanity") or {},
                "arithmeticConsistency": evaluation.get("arithmetic_consistency") or evaluation.get("arithmeticConsistency") or {},
                "quantityCoherence": evaluation.get("quantity_coherence") or evaluation.get("quantityCoherence") or {},
                "ruleOutcomes": _normalize_rule_outcomes(
                    evaluation.get("rule_compliance"),
                    source_type="correctness",
                    source_label=f"Correctness #{index + 1}",
                ),
            }
        )

    severity_order = {
        "NOT_APPLICABLE": 0,
        "PASS": 1,
        "SOFT_FAIL": 2,
        "HARD_FAIL": 3,
        "CRITICAL": 4,
    }
    worst_verdict = normalize_correctness_verdict(row_worst_correctness)
    for evaluation in normalized_evaluations:
        verdict = evaluation["verdict"]
        if verdict is None:
            continue
        if worst_verdict is None or severity_order.get(verdict, -1) > severity_order.get(worst_verdict, -1):
            worst_verdict = verdict

    return {
        "worstVerdict": worst_verdict,
        "evaluations": normalized_evaluations,
    }


def build_canonical_thread_evaluation(
    result: dict[str, Any] | None,
    *,
    row_intent_accuracy: float | None = None,
    row_worst_correctness: str | None = None,
    row_efficiency_verdict: str | None = None,
    row_success_status: bool | None = None,
) -> dict[str, Any]:
    payload = dict(result or {})
    existing = payload.get("canonical_thread") or payload.get("canonicalThread")
    if isinstance(existing, dict) and {"facts", "evaluators", "derived"} <= set(existing.keys()):
        return existing
    if {"facts", "evaluators", "derived"} <= set(payload.keys()):
        return payload

    facts = {
        "thread": _normalize_thread_facts(payload),
        "execution": {
            "failedEvaluators": dict(payload.get("failed_evaluators") or payload.get("failedEvaluators") or {}),
            "skippedEvaluators": list(payload.get("skipped_evaluators") or payload.get("skippedEvaluators") or []),
            "hadEvaluationError": bool(payload.get("error") or payload.get("failed_evaluators") or payload.get("failedEvaluators")),
        },
    }

    evaluators = {
        "intent": _normalize_intent_block(payload, row_intent_accuracy=row_intent_accuracy),
        "efficiency": _normalize_efficiency_block(payload, row_efficiency_verdict=row_efficiency_verdict),
        "correctness": _normalize_correctness_block(payload, row_worst_correctness=row_worst_correctness),
        "custom": dict(payload.get("custom_evaluations") or payload.get("customEvaluations") or {}),
    }

    per_source_rule_outcomes = list(evaluators["efficiency"]["ruleOutcomes"])
    for evaluation in evaluators["correctness"]["evaluations"]:
        per_source_rule_outcomes.extend(evaluation["ruleOutcomes"])
    canonical_rule_outcomes, rule_summary = _aggregate_rule_outcomes(per_source_rule_outcomes)

    success_status = payload.get("success_status")
    if success_status is None:
        success_status = row_success_status

    derived = {
        "successStatus": bool(success_status),
        "worstCorrectnessVerdict": evaluators["correctness"]["worstVerdict"],
        "efficiencyVerdict": evaluators["efficiency"]["verdict"],
        "canonicalRuleOutcomes": canonical_rule_outcomes,
        "ruleComplianceSummary": rule_summary,
    }

    return {
        "version": 1,
        "facts": facts,
        "evaluators": evaluators,
        "derived": derived,
    }


def enrich_thread_result_for_api(
    result: dict[str, Any] | None,
    *,
    row_intent_accuracy: float | None = None,
    row_worst_correctness: str | None = None,
    row_efficiency_verdict: str | None = None,
    row_success_status: bool | None = None,
) -> dict[str, Any]:
    enriched = dict(result or {})
    canonical_thread = build_canonical_thread_evaluation(
        enriched,
        row_intent_accuracy=row_intent_accuracy,
        row_worst_correctness=row_worst_correctness,
        row_efficiency_verdict=row_efficiency_verdict,
        row_success_status=row_success_status,
    )
    enriched["canonical_thread"] = canonical_thread
    return enriched
