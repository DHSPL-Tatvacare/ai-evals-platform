# backend/app/services/reports/flag_utils.py
"""Reusable flag aggregation with dual-denominator (reach + conversion) support.

Handles the 'not_relevant' pattern: flags where the signal didn't apply to a call
are excluded from denominators so agents aren't penalized for things that never arose.
"""

from __future__ import annotations


def aggregate_flag(
    items: list[dict],
    present_key: str = "present",
) -> dict:
    """Aggregate boolean flags with not_relevant support.

    Returns: { relevant, notRelevant, present }
    """
    relevant = 0
    not_relevant = 0
    present = 0

    for item in items:
        val = item.get(present_key)
        if val == "not_relevant":
            not_relevant += 1
        else:
            relevant += 1
            if val is True:
                present += 1

    return {"relevant": relevant, "notRelevant": not_relevant, "present": present}


def aggregate_outcome_flag(
    items: list[dict],
    attempted_key: str = "attempted",
    accepted_key: str | None = "accepted",
) -> dict:
    """Aggregate outcome flags with reach + conversion denominators.

    Returns: { relevant, notRelevant, attempted, accepted }
    """
    relevant = 0
    not_relevant = 0
    attempted = 0
    accepted = 0

    for item in items:
        val = item.get(attempted_key)
        if val == "not_relevant":
            not_relevant += 1
        else:
            relevant += 1
            if val is True:
                attempted += 1
                if accepted_key and item.get(accepted_key) is True:
                    accepted += 1

    return {
        "relevant": relevant,
        "notRelevant": not_relevant,
        "attempted": attempted,
        "accepted": accepted,
    }
