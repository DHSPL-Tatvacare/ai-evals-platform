"""Phase 1A follow-up — as_tool output extractor pulls submit_sql JSON.

Investigation (2026-05-10): when the supervisor calls ``data_specialist``
via ``Agent.as_tool``, the SDK's documented default is "last message
from the agent will be used" as the tool output. That swallows the
``SpecialistResult`` JSON that ``submit_sql`` produced, and the
supervisor sees only the LLM's prose. Downstream the wire event for
``specialist_finished`` carries empty evidence_refs / artifact_refs /
0ms duration, and ``artifact_emitted`` never fires for chart payloads.

This test pins the extractor that fixes the boundary loss:
``extract_data_specialist_output`` walks ``RunResult.new_items``
backward, finds the most recent ``submit_sql`` ToolCallOutputItem (joined
to its call via the shared call_id -> name index), and returns its raw
JSON string. Falls back to ``final_output`` text when no submit_sql output
exists, then to a refusal SpecialistResult JSON when there is no usable
text either (S1-3 invariant: no blank error card).

Fixtures model the real SDK shape: tool_call_item carries `name` +
`call_id`; tool_call_output_item carries `call_id` only.
"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from typing import Any


from app.services.sherlock_v3.data_specialist import (
    extract_data_specialist_output,
)


# ── stubs that mimic the SDK shapes the extractor reads ────────────


def _tool_call(name: str, call_id: str) -> SimpleNamespace:
    """Mirror SDK ToolCallItem: raw_item carries `name` + `call_id`."""
    return SimpleNamespace(
        type='tool_call_item',
        raw_item={'name': name, 'call_id': call_id},
    )


def _tool_output(call_id: str, output: Any) -> SimpleNamespace:
    """Mirror SDK ToolCallOutputItem: raw_item carries ONLY `call_id`."""
    return SimpleNamespace(
        type='tool_call_output_item',
        raw_item={'call_id': call_id},
        output=output,
    )


def _message() -> SimpleNamespace:
    return SimpleNamespace(type='message_output_item')


def _run(new_items: list[Any], final_output: Any = 'fallback message') -> SimpleNamespace:
    return SimpleNamespace(new_items=new_items, final_output=final_output)


# ── tests ──────────────────────────────────────────────────────────


class ExtractorPullsLastSubmitSqlOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_last_submit_sql_output_string(self) -> None:
        first_payload = json.dumps({
            'kind': 'data', 'status': 'error', 'summary': 'first try failed',
            'evidence': [], 'artifacts': [], 'meta': {},
        })
        second_payload = json.dumps({
            'kind': 'data', 'status': 'ok', 'summary': '16 rows',
            'evidence': [{'ref_id': 'ev1'}],
            'artifacts': [{'kind': 'chart', 'payload': {'kind': 'chart'}}],
            'meta': {'latency_ms': 56},
        })
        run = _run(new_items=[
            _message(),
            _tool_call('submit_sql', 'c1'),
            _tool_output('c1', first_payload),
            _message(),
            _tool_call('submit_sql', 'c2'),
            _tool_output('c2', second_payload),
            _message(),  # data_specialist's final answer message
        ])

        result = await extract_data_specialist_output(run)

        self.assertEqual(result, second_payload)
        # Roundtrips to the SpecialistResult shape so the supervisor
        # boundary picks up evidence + artifacts.
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'ok')
        self.assertEqual(decoded['evidence'][0]['ref_id'], 'ev1')
        self.assertEqual(decoded['meta']['latency_ms'], 56)


class ExtractorFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_tool_output_returns_final_output_text(self) -> None:
        # Clarifying-question turn: the LLM answered without calling
        # submit_sql. The extractor returns the final-answer text so
        # the SDK's default behaviour is preserved.
        run = _run(
            new_items=[_message(), _message()],
            final_output='Could you clarify which app you mean?',
        )
        result = await extract_data_specialist_output(run)
        self.assertEqual(result, 'Could you clarify which app you mean?')

    async def test_dict_output_serialized_as_json(self) -> None:
        # Belt-and-braces: if a future SDK change hands us a dict
        # instead of a string, json-serialize it so ``json.loads``
        # downstream still works.
        payload_dict = {'kind': 'data', 'status': 'ok', 'summary': 'x'}
        run = _run(new_items=[
            _tool_call('submit_sql', 'c1'),
            _tool_output('c1', payload_dict),
        ])
        result = await extract_data_specialist_output(run)
        self.assertEqual(json.loads(result), payload_dict)

    async def test_empty_new_items_no_text_returns_refusal(self) -> None:
        # S1-3: no tool output and no usable text -> refusal SpecialistResult.
        run = _run(new_items=[], final_output='')
        result = await extract_data_specialist_output(run)
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'error')
        self.assertNotEqual(decoded['summary'], '')

    async def test_non_string_final_output_returns_refusal(self) -> None:
        # S1-3: a None final_output with no tool output -> refusal JSON.
        run = _run(new_items=[], final_output=None)
        result = await extract_data_specialist_output(run)
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'error')
        self.assertNotEqual(decoded['summary'], '')


class ExtractorMatchesByCallIdIndexTests(unittest.IsolatedAsyncioTestCase):
    async def test_matches_submit_sql_via_call_id_index(self) -> None:
        run = _run(new_items=[
            _tool_call('submit_sql', 'c1'),
            _tool_output('c1', '{"kind":"data","status":"ok"}'),
        ])
        result = await extract_data_specialist_output(run)
        self.assertEqual(result, '{"kind":"data","status":"ok"}')

    async def test_attribute_style_raw_items_match(self) -> None:
        call = SimpleNamespace(
            type='tool_call_item',
            raw_item=SimpleNamespace(name='submit_sql', call_id='c1'),
        )
        out = SimpleNamespace(
            type='tool_call_output_item',
            raw_item=SimpleNamespace(call_id='c1'),
            output='{"kind":"data","status":"ok"}',
        )
        run = _run(new_items=[call, out])
        result = await extract_data_specialist_output(run)
        self.assertEqual(result, '{"kind":"data","status":"ok"}')


if __name__ == '__main__':
    unittest.main()
