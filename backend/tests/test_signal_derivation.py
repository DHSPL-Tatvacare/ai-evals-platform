"""Unit tests for the signal derivation framework (Phase 11A).

Covers the ``rule`` strategy plugin and the seeded ``mql`` definition.
This replaces ``test_mql_score.py`` — the hardcoded ``compute_mql_score``
is gone; ``mql`` is now a ``rule`` signal definition, so the behaviour it
used to guarantee is asserted here against the definition + strategy.
"""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.services.analytics.signal_derivation.base import StrategyContext
from app.services.analytics.signal_derivation.definition_seed import (
    MQL_DEFINITION_BODY,
)
from app.services.analytics.signal_derivation.registry import get_strategy
from app.services.analytics.signal_derivation.rule_strategy import RuleStrategy

_TS = datetime(2026, 5, 14, tzinfo=timezone.utc)


def _lead(**attrs_first_seen) -> dict:
    """A dim_lead-shaped source row. ``city`` is a top-level identity
    column; the MQL-input keys live in ``attributes_at_first_seen``."""
    city = attrs_first_seen.pop("city", None)
    return {
        "lead_id": "L-1",
        "first_seen_at": _TS,
        "city": city,
        "attributes_at_first_seen": dict(attrs_first_seen),
    }


async def _derive(row: dict) -> dict[str, str | None]:
    strategy = get_strategy("rule")
    ctx = StrategyContext(tenant_id=uuid.uuid4(), app_id="inside-sales")
    signals = await strategy.derive(
        definition=MQL_DEFINITION_BODY, source_rows=[row], ctx=ctx
    )
    return {s.signal_type: s.signal_value for s in signals}


class RuleStrategyValidationTests(unittest.TestCase):
    def test_mql_seed_body_validates(self) -> None:
        # The shipped seed must always satisfy the strategy it targets.
        get_strategy("rule").validate(MQL_DEFINITION_BODY)

    def test_rejects_empty_signals(self) -> None:
        with self.assertRaises(Exception):
            RuleStrategy().validate({"signals": []})

    def test_rejects_unknown_predicate(self) -> None:
        with self.assertRaises(Exception):
            RuleStrategy().validate(
                {"signals": [{"signal_type": "x", "field": "city",
                              "predicate": "regex_match", "args": {}}]}
            )

    def test_rejects_duplicate_signal_type(self) -> None:
        with self.assertRaises(Exception):
            RuleStrategy().validate(
                {"signals": [
                    {"signal_type": "x", "field": "city",
                     "predicate": "in_set", "args": {"values": []}},
                    {"signal_type": "x", "field": "city",
                     "predicate": "in_set", "args": {"values": []}},
                ]}
            )

    def test_rejects_deep_field_path(self) -> None:
        with self.assertRaises(Exception):
            RuleStrategy().validate(
                {"signals": [{"signal_type": "x",
                              "field": "a.b.c", "predicate": "in_set",
                              "args": {"values": []}}]}
            )


class MqlBehaviourTests(unittest.IsolatedAsyncioTestCase):
    """The behaviour the old compute_mql_score guaranteed, asserted via
    the rule strategy + the seeded mql definition."""

    async def test_all_five_signals_fire(self) -> None:
        out = await _derive(_lead(
            age_group="31-40",
            city="Mumbai",
            condition="Type 2 Diabetes",
            hba1c_band="6.5 - 8.0",
            intent_to_pay="yes, interested",
        ))
        for st in ("mql_age", "mql_city", "mql_condition",
                   "mql_hba1c", "mql_intent"):
            self.assertEqual(out[st], "true", st)
        self.assertEqual(out["mql_score"], "5")

    async def test_nothing_fires_on_empty_lead(self) -> None:
        out = await _derive(_lead())
        for st in ("mql_age", "mql_city", "mql_condition",
                   "mql_hba1c", "mql_intent"):
            self.assertEqual(out[st], "false", st)
        self.assertEqual(out["mql_score"], "0")

    async def test_age_band_out_of_range(self) -> None:
        out = await _derive(_lead(age_group="18-30"))
        self.assertEqual(out["mql_age"], "false")

    async def test_city_case_insensitive(self) -> None:
        out = await _derive(_lead(city="PUNE"))
        self.assertEqual(out["mql_city"], "true")

    async def test_city_not_in_target_list(self) -> None:
        out = await _derive(_lead(city="Tumkur"))
        self.assertEqual(out["mql_city"], "false")

    async def test_condition_substring_match(self) -> None:
        out = await _derive(_lead(condition="diagnosed with PCOS last year"))
        self.assertEqual(out["mql_condition"], "true")

    async def test_hba1c_below_threshold(self) -> None:
        out = await _derive(_lead(hba1c_band="5.0 - 5.6 (normal)"))
        self.assertEqual(out["mql_hba1c"], "false")

    async def test_hba1c_at_threshold(self) -> None:
        out = await _derive(_lead(hba1c_band="5.7 - 6.4 (pre-diabetes)"))
        self.assertEqual(out["mql_hba1c"], "true")

    async def test_intent_negative_does_not_fire(self) -> None:
        out = await _derive(_lead(intent_to_pay="no, not right now"))
        self.assertEqual(out["mql_intent"], "false")

    async def test_intent_present_and_positive_fires(self) -> None:
        out = await _derive(_lead(intent_to_pay="maybe later"))
        self.assertEqual(out["mql_intent"], "true")

    async def test_partial_score(self) -> None:
        out = await _derive(_lead(city="Mumbai", age_group="31-40"))
        self.assertEqual(out["mql_score"], "2")

    async def test_signal_value_numeric_mirrors_boolean(self) -> None:
        strategy = get_strategy("rule")
        ctx = StrategyContext(tenant_id=uuid.uuid4(), app_id="inside-sales")
        signals = await strategy.derive(
            definition=MQL_DEFINITION_BODY,
            source_rows=[_lead(city="Mumbai")],
            ctx=ctx,
        )
        by_type = {s.signal_type: s for s in signals}
        self.assertEqual(by_type["mql_city"].signal_value_numeric, Decimal(1))
        self.assertEqual(by_type["mql_age"].signal_value_numeric, Decimal(0))
        self.assertEqual(by_type["mql_score"].signal_value_numeric, Decimal(1))
        # detected_at is the source row's first_seen_at — stable across reruns.
        self.assertEqual(by_type["mql_city"].detected_at, _TS)

    async def test_row_without_lead_identity_is_skipped(self) -> None:
        strategy = get_strategy("rule")
        ctx = StrategyContext(tenant_id=uuid.uuid4(), app_id="inside-sales")
        signals = await strategy.derive(
            definition=MQL_DEFINITION_BODY,
            source_rows=[{"lead_id": None, "first_seen_at": _TS,
                          "attributes_at_first_seen": {}}],
            ctx=ctx,
        )
        self.assertEqual(signals, [])


if __name__ == "__main__":
    unittest.main()
