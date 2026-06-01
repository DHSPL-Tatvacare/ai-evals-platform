"""Step 2 — the context ring must read EXACT occupancy: the LAST model
response's input tokens, not the run-aggregate across all the turn's calls.

``previous_response_id`` re-bills the full context on every model call, so the
aggregate over-counts occupancy. These tests pin ``_extract_usage`` to the
last response's input figure as ``occupancy_input_tokens`` (None-safe fallback to
the aggregate) while ``input_tokens`` and the other aggregate fields stay intact
for cost / per-turn usage display.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from agents.usage import Usage
from openai.types.responses.response_usage import InputTokensDetails

from app.services.sherlock_v3.runtime import _extract_usage


def _model_response(input_tokens: int, cached: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        usage=Usage(
            requests=1,
            input_tokens=input_tokens,
            input_tokens_details=InputTokensDetails(cached_tokens=cached),
        )
    )


def _streaming(*, aggregate: Usage, raw_responses: list) -> SimpleNamespace:
    return SimpleNamespace(
        context_wrapper=SimpleNamespace(usage=aggregate),
        raw_responses=raw_responses,
    )


class RingLastResponseUsageTests(unittest.TestCase):
    def test_ring_uses_last_response_not_turn_aggregate(self) -> None:
        aggregate = Usage(
            requests=2,
            input_tokens=2500,
            output_tokens=300,
            input_tokens_details=InputTokensDetails(cached_tokens=400),
        )
        streaming = _streaming(
            aggregate=aggregate,
            raw_responses=[_model_response(1000), _model_response(1500)],
        )

        usage = _extract_usage(streaming)

        # Ring occupancy = last response (1500), NOT the sum (2500).
        self.assertEqual(usage['occupancy_input_tokens'], 1500)
        # input_tokens stays the aggregate for cost / per-turn usage display.
        self.assertEqual(usage['input_tokens'], 2500)
        self.assertEqual(usage['output_tokens'], 300)
        self.assertEqual(usage['cached_read_tokens'], 400)
        self.assertEqual(usage['call_count'], 2)

    def test_falls_back_to_aggregate_when_no_raw_responses(self) -> None:
        aggregate = Usage(requests=1, input_tokens=900, output_tokens=120)
        streaming = _streaming(aggregate=aggregate, raw_responses=[])

        usage = _extract_usage(streaming)

        self.assertEqual(usage['occupancy_input_tokens'], 900)
        self.assertEqual(usage['input_tokens'], 900)

    def test_falls_back_when_last_response_has_no_usage(self) -> None:
        aggregate = Usage(requests=1, input_tokens=700)
        streaming = _streaming(
            aggregate=aggregate,
            raw_responses=[SimpleNamespace(usage=None)],
        )

        usage = _extract_usage(streaming)

        self.assertEqual(usage['occupancy_input_tokens'], 700)
        self.assertEqual(usage['input_tokens'], 700)

    def test_none_usage_returns_zeroes(self) -> None:
        streaming = SimpleNamespace(context_wrapper=None, raw_responses=[])

        usage = _extract_usage(streaming)

        self.assertEqual(usage['occupancy_input_tokens'], 0)
        self.assertEqual(usage['input_tokens'], 0)
        self.assertEqual(usage['cached_read_tokens'], 0)
        self.assertEqual(usage['call_count'], 0)


if __name__ == '__main__':
    unittest.main()
