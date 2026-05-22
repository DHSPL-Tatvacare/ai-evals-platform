"""Phase 1 Step 6 — extract_authoring_specialist_output strict matching.

Models the real OpenAI Agents SDK shape: tool_call_item carries `name` +
`call_id`; tool_call_output_item carries `call_id` only. The extractor
joins them via a per-run call_id -> name index. The original v1 fixture
that put `name` directly on the output item modeled a shape the SDK does
not produce, so tests passed while production silently fell through to
final_output prose. This file reflects the production reality.
"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from app.services.sherlock_v3.authoring_specialist import (
    extract_authoring_specialist_output,
)


def _tool_call(name: str, call_id: str) -> SimpleNamespace:
    """Mirror SDK ToolCallItem: raw_item carries `name` + `call_id`."""
    return SimpleNamespace(
        type='tool_call_item',
        raw_item={'name': name, 'call_id': call_id},
    )


def _tool_output(call_id: str, output: str) -> SimpleNamespace:
    """Mirror SDK ToolCallOutputItem: raw_item carries ONLY `call_id`."""
    return SimpleNamespace(
        type='tool_call_output_item',
        raw_item={'call_id': call_id},
        output=output,
    )


def _pair(name: str, call_id: str, output: str) -> list[SimpleNamespace]:
    """A complete call+output pair as the SDK actually emits them."""
    return [_tool_call(name, call_id), _tool_output(call_id, output)]


class AuthoringSpecialistExtractorTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_apply_patch_output_when_present(self) -> None:
        run_result = SimpleNamespace(
            new_items=[
                *_pair('list_node_types', 'c1', '{"items": []}'),
                *_pair('apply_patch', 'c2', json.dumps({
                    'kind': 'action', 'status': 'ok',
                    'summary': 'patched', 'artifacts': [], 'evidence': [],
                    'meta': {},
                })),
            ],
            final_output='ignored prose',
        )
        result = await extract_authoring_specialist_output(run_result)
        decoded = json.loads(result)
        self.assertEqual(decoded['summary'], 'patched')

    async def test_returns_most_recent_apply_patch_when_multiple(self) -> None:
        run_result = SimpleNamespace(
            new_items=[
                *_pair('apply_patch', 'c1', '{"summary": "first"}'),
                *_pair('apply_patch', 'c2', '{"summary": "second"}'),
            ],
            final_output='',
        )
        result = await extract_authoring_specialist_output(run_result)
        self.assertIn('second', result)
        self.assertNotIn('first', result)

    async def test_does_not_pick_lookup_output_strict_match(self) -> None:
        """Critical regression: a lookup tool's output MUST NOT be returned
        as the apply_patch payload, even when it's the only output present."""
        run_result = SimpleNamespace(
            new_items=[
                *_pair('list_provider_connections', 'c1', '{"items": []}'),
            ],
            final_output='Which app should this connect to?',
        )
        result = await extract_authoring_specialist_output(run_result)
        self.assertEqual(result, 'Which app should this connect to?')

    async def test_falls_back_to_final_output_when_no_apply_patch(self) -> None:
        # Clarifying-question turn: lookups + final prose, no apply_patch.
        run_result = SimpleNamespace(
            new_items=[
                *_pair('list_provider_connections', 'c1', '{"items": []}'),
                *_pair('list_cohort_datasets', 'c2', '{"items": []}'),
            ],
            final_output='Which connection should I use?',
        )
        result = await extract_authoring_specialist_output(run_result)
        self.assertEqual(result, 'Which connection should I use?')

    async def test_returns_empty_string_when_no_items_no_final(self) -> None:
        run_result = SimpleNamespace(new_items=[], final_output=None)
        result = await extract_authoring_specialist_output(run_result)
        self.assertEqual(result, '')

    async def test_handles_attribute_style_raw_items(self) -> None:
        """Some SDK builds expose raw_item as an object, not a dict.
        Extractor must handle both shapes."""
        call = SimpleNamespace(
            type='tool_call_item',
            raw_item=SimpleNamespace(name='apply_patch', call_id='c1'),
        )
        output = SimpleNamespace(
            type='tool_call_output_item',
            raw_item=SimpleNamespace(call_id='c1'),
            output='{"summary": "attr-style"}',
        )
        run_result = SimpleNamespace(
            new_items=[call, output], final_output='',
        )
        result = await extract_authoring_specialist_output(run_result)
        self.assertIn('attr-style', result)

    async def test_skips_orphan_output_with_unknown_call_id(self) -> None:
        """An output_item whose call_id has no matching tool_call_item
        must NOT match — guards against malformed runs leaking lookup
        outputs as if they were apply_patch."""
        run_result = SimpleNamespace(
            new_items=[
                # No matching tool_call_item for c_orphan
                _tool_output('c_orphan', '{"summary": "orphan"}'),
            ],
            final_output='fell back',
        )
        result = await extract_authoring_specialist_output(run_result)
        self.assertEqual(result, 'fell back')


class BuildAuthoringSpecialistImportTests(unittest.TestCase):
    def test_module_imports_without_side_effects(self) -> None:
        # Build path imports the pack, which auto-registers; the import
        # alone should not raise even with no DB available.
        from app.services.sherlock_v3 import authoring_specialist  # noqa: F401
        self.assertTrue(hasattr(authoring_specialist, 'build_authoring_specialist'))


if __name__ == '__main__':
    unittest.main()
