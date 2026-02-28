"""Weighted health score calculator.

Pure function — no DB access, no LLM calls.
Takes pre-extracted summary values, returns a HealthScore model.
"""

from .schemas import HealthScore, HealthScoreBreakdown, HealthScoreBreakdownItem

GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (95, "A+"), (90, "A"), (85, "A-"),
    (80, "B+"), (75, "B"), (70, "B-"),
    (65, "C+"), (60, "C"), (55, "C-"),
    (50, "D+"), (45, "D"), (0, "F"),
]


def compute_health_score(
    avg_intent_accuracy: float | None,
    correctness_verdicts: dict[str, int],
    efficiency_verdicts: dict[str, int],
    total_evaluated: int,
    success_count: int,
) -> HealthScore:
    """Compute weighted health score from summary metrics.

    Args:
        avg_intent_accuracy: Average intent accuracy across threads (0–1 scale), or None.
        correctness_verdicts: e.g. {"PASS": 10, "SOFT FAIL": 2, "HARD FAIL": 1}.
        efficiency_verdicts: e.g. {"EFFICIENT": 8, "ACCEPTABLE": 3, "FRICTION": 1}.
        total_evaluated: Total threads that were evaluated (denominator).
        success_count: Threads where task_completed=True.

    Returns:
        HealthScore with grade, numeric score, and per-dimension breakdown.
    """
    denom = max(total_evaluated, 1)

    # When a dimension has no data (e.g. intent not evaluated), exclude it
    # from scoring and redistribute its weight equally among active dimensions.
    has_intent = avg_intent_accuracy is not None
    has_correctness = bool(correctness_verdicts)
    has_efficiency = bool(efficiency_verdicts)

    active_count = sum([has_intent, has_correctness, has_efficiency, True])  # task_completion always active
    weight = 1.0 / active_count

    intent = (avg_intent_accuracy or 0) * 100 if has_intent else 0.0
    correct = (correctness_verdicts.get("PASS", 0) / denom) * 100 if has_correctness else 0.0
    efficient = (
        (efficiency_verdicts.get("EFFICIENT", 0) + efficiency_verdicts.get("ACCEPTABLE", 0))
        / denom
    ) * 100 if has_efficiency else 0.0
    task_comp = (success_count / denom) * 100

    numeric = (
        (intent * weight if has_intent else 0)
        + (correct * weight if has_correctness else 0)
        + (efficient * weight if has_efficiency else 0)
        + task_comp * weight
    )

    grade = next(g for threshold, g in GRADE_THRESHOLDS if numeric >= threshold)

    return HealthScore(
        grade=grade,
        numeric=round(numeric, 1),
        breakdown=HealthScoreBreakdown(
            intent_accuracy=HealthScoreBreakdownItem(
                value=round(intent, 1),
                weighted=round(intent * weight if has_intent else 0, 1),
            ),
            correctness_rate=HealthScoreBreakdownItem(
                value=round(correct, 1),
                weighted=round(correct * weight if has_correctness else 0, 1),
            ),
            efficiency_rate=HealthScoreBreakdownItem(
                value=round(efficient, 1),
                weighted=round(efficient * weight if has_efficiency else 0, 1),
            ),
            task_completion=HealthScoreBreakdownItem(
                value=round(task_comp, 1),
                weighted=round(task_comp * weight, 1),
            ),
        ),
    )
