"""Verbatim-fixture parser tests for the Phase-2 backfill (OLD stored JSON → EvaluationDrafts).

Fixtures mirror the exact key/value shapes of real rows in platform.evaluation_run_thread_results /
evaluation_run_adversarial_results / evaluation_runs (sampled from the docker-compose DB, 2026-06-03).
Parsers are keyed by eval_type — the only app-aware code in this leg.
"""
from __future__ import annotations

from app.services.evaluators.backfill.parsers import (
    parse_batch_adversarial,
    parse_batch_thread,
    parse_call_quality,
    parse_custom,
    parse_full_evaluation,
)

# --- verbatim batch_thread (kaira) thread_result.result slice ---
BATCH_THREAD_RESULT = {
    "thread": {"thread_id": "thrd-80ddb45f", "__type__": "ConversationThread"},
    "correctness_evaluations": [
        {
            "__type__": "CorrectnessEvaluation",
            "verdict": "PASS",
            "reasoning": "Consistent and plausible.",
            "rule_compliance": [
                {"status": "FOLLOWED", "rule_id": "exact_calorie_values",
                 "section": "Nutrition Data Context", "evidence": "Used exact value.", "followed": True},
                {"status": "NOT_APPLICABLE", "rule_id": "composite_dish_single_item",
                 "section": "Food Processing Instructions", "evidence": "Single item.", "followed": None},
                {"status": "VIOLATED", "rule_id": "single_item_one_table",
                 "section": "Table Formatting", "evidence": "Two tables.", "followed": False},
            ],
        },
        {"__type__": "CorrectnessEvaluation", "verdict": "HARD FAIL", "rule_compliance": []},
    ],
    "efficiency_evaluation": {
        "__type__": "EfficiencyEvaluation",
        "verdict": "INCOMPLETE",
        "reasoning": "Ended at confirmation.",
        "rule_compliance": [
            {"status": "FOLLOWED", "rule_id": "minimal_turns", "section": "Efficiency",
             "evidence": "One turn.", "followed": True},
        ],
    },
    "intent_evaluations": [
        {"__type__": "IntentEvaluation", "predicted_intent": "FoodAgent", "is_correct_intent": True},
        {"__type__": "IntentEvaluation", "predicted_intent": "FoodAgent", "is_correct_intent": False},
    ],
    "custom_evaluations": None,
}

# --- verbatim call_quality (inside-sales) thread_result.result slice ---
CALL_QUALITY_RESULT = {
    "transcript": "...",
    "call_metadata": {"duration": 42},
    "evaluations": [
        {
            "evaluator_name": "Call Quality Rubric",
            "evaluator_id": "11111111-1111-1111-1111-111111111111",
            "output": {
                "overall_score": 6.67,
                "reasoning": [
                    {"max": 10, "score": 7, "dimension": "Call Opening & Permission",
                     "explanation": "Introduced herself clearly."},
                    {"max": 15, "score": 0, "dimension": "Brand Positioning & Promise",
                     "explanation": "Call ended before this."},
                ],
            },
        },
    ],
}

# --- verbatim batch_adversarial (kaira) adversarial_result.result slice ---
ADVERSARIAL_RESULT = {
    "__type__": "AdversarialEvaluation",
    "verdict": "PASS",
    "goal_achieved": True,
    "reasoning": "Bot logged the meal.",
    "transcript": [{"role": "user", "content": "I had an apple."}],
    "raw_judge_output": "ok",
    "test_case": {
        "__type__": "AdversarialTestCase",
        "goal_flow": ["meal_logged"],
        "difficulty": "EASY",
        "active_traits": [],
        "persona_labels": ["easy"],
        "synthetic_input": "I had an apple for breakfast.",
    },
    "rule_compliance": [
        {"status": "FOLLOWED", "rule_id": "ask_quantity", "section": "Logging",
         "evidence": "Asked for quantity.", "followed": True},
        {"status": "VIOLATED", "rule_id": "no_medical_advice", "section": "Safety",
         "evidence": "Gave advice.", "followed": False},
    ],
}

# --- verbatim full_evaluation (voice-rx) run.result + summary slice ---
FULL_EVAL_RESULT = {
    "flowType": "prescription",
    "id": "0e1d1118-9dc7-48a8-bf17-7f3e5574aca4",
    "judgeOutput": {"raw": "..."},
    "prompts": {"system": "..."},
    "transcriptComparison": "...",
    "critique": {
        "segments": [
            {"severity": "CRITICAL", "confidence": 0.9, "segmentIndex": 4,
             "discrepancy": "10x dosage error", "judgeText": "5mg", "originalText": "50mg",
             "category": "dosage", "likelyCorrect": False},
        ],
        "fieldCritiques": [
            {"severity": "moderate", "critique": "Wrong unit", "fieldPath": "medication.dose",
             "apiValue": "50mg", "judgeValue": "5mg", "match": False, "confidence": 0.8},
        ],
    },
}
FULL_EVAL_SUMMARY = {"overall_accuracy": 0.5, "critical_errors": 1, "flow_type": "prescription"}

# --- verbatim custom (voice-rx) run.result + summary slice ---
CUSTOM_RESULT = {
    "rawRequest": {"transcript": "..."},
    "rawResponse": {"raw": "..."},
    "output": {
        "factual_accuracy_pct": 80,
        "errors": [
            {"entity": "olsar 10 mg", "output_says": "active medication for 1 year",
             "source_says": "stopped taking 1 year ago", "output_timing": "current", "source_timing": "past"},
        ],
        "reasoning": "One temporal error.",
    },
}
CUSTOM_SUMMARY = {
    "overall_score": 80.0,
    "max_score": 100.0,
    "reasoning": "Mostly accurate.",
    "metadata": {"main_metric_key": "factual_accuracy_pct", "main_metric_type": "number"},
}


def test_batch_thread_three_evaluators_rule_and_dimension():
    drafts = parse_batch_thread("thrd-80ddb45f", BATCH_THREAD_RESULT)
    by_name = {d.evaluator.name: d for d in drafts}
    assert set(by_name) == {"correctness", "efficiency", "intent"}

    # correctness → rule atoms, worst verdict headline
    corr = by_name["correctness"]
    assert {a.style for a in corr.details} == {"rule"}
    statuses = sorted(a.status for a in corr.details)
    assert statuses == ["FAIL", "NA", "PASS"]
    assert corr.headline.verdict == "HARD FAIL"  # worst of PASS / HARD FAIL

    # efficiency → rule atoms + verdict headline
    eff = by_name["efficiency"]
    assert [a.status for a in eff.details] == ["PASS"]
    assert eff.headline.verdict == "INCOMPLETE"

    # intent → one dimension atom, accuracy = 1/2
    intent = by_name["intent"]
    assert len(intent.details) == 1
    assert intent.details[0].style == "dimension"
    assert intent.details[0].is_main is True
    assert abs(intent.details[0].score - 0.5) < 1e-9


def test_batch_thread_target_is_thread():
    drafts = parse_batch_thread("thrd-80ddb45f", BATCH_THREAD_RESULT)
    assert all(d.target.key == "thrd-80ddb45f" for d in drafts)
    assert all(d.target.type == "chat_thread" for d in drafts)


def test_call_quality_dimensions_and_main():
    drafts = parse_call_quality("call-1", CALL_QUALITY_RESULT)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.evaluator.name == "Call Quality Rubric"
    assert {a.style for a in d.details} == {"dimension"}
    main = [a for a in d.details if a.is_main]
    assert len(main) == 1 and main[0].key == "overall_score"
    rapport = next(a for a in d.details if a.key == "Call Opening & Permission")
    assert rapport.score == 7 and rapport.max == 10
    assert float(d.headline.score) == 6.67


def test_adversarial_rules_and_goal_headline():
    drafts = parse_batch_adversarial("42", ADVERSARIAL_RESULT)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.target.key == "42" and d.target.type == "test_case"
    assert d.target.attributes["difficulty"] == "EASY"
    assert {a.status for a in d.details} == {"PASS", "FAIL"}
    assert d.headline.verdict == "PASS"
    assert d.headline.score == 1.0
    assert d.raw_payload["transcript"] == [{"role": "user", "content": "I had an apple."}]


def test_full_evaluation_comparison_atoms():
    drafts = parse_full_evaluation("call-9", FULL_EVAL_RESULT, FULL_EVAL_SUMMARY)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.target.type == "transcript"
    styles = {a.style for a in d.details}
    assert styles == {"comparison"}
    seg = next(a for a in d.details if a.locator == "segment:4")
    assert seg.severity == "critical"
    assert seg.reference_text == "50mg" and seg.candidate_text == "5mg"
    fc = next(a for a in d.details if a.locator.startswith("api_field:"))
    assert fc.severity == "moderate"
    assert fc.reference_text == "5mg" and fc.candidate_text == "50mg"
    assert float(d.headline.score) == 0.5


def test_custom_errors_to_comparison():
    drafts = parse_custom("call-3", CUSTOM_RESULT, CUSTOM_SUMMARY)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.target.type == "transcript"
    assert len(d.details) == 1
    err = d.details[0]
    assert err.style == "comparison"
    assert err.key == "olsar 10 mg"
    assert err.reference_text == "stopped taking 1 year ago"
    assert err.candidate_text == "active medication for 1 year"
    assert d.headline.key == "factual_accuracy_pct"
    assert float(d.headline.score) == 80.0
    assert d.raw_payload["rawRequest"] == {"transcript": "..."}


def test_empty_results_yield_no_drafts():
    assert parse_batch_thread("t", {}) == []
    assert parse_call_quality("t", {"evaluations": []}) == []
    assert parse_custom("r", {"output": {}}, {}) == []
