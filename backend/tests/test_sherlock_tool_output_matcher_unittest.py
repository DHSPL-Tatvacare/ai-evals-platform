"""S1-4 — uniform SAFE tool-output matcher (one shared function).

The shared matcher in ``sherlock_v3/tool_output.py`` joins a run's
``tool_call_output_item``s back to the tool that produced them via a
call_id -> tool_name index, and returns ``False`` on any miss. This
replaces data_specialist's old ``True`` catch-all that would have leaked
the wrong shape the moment a second tool was added.
"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from app.services.sherlock_v3.data_specialist import (
    extract_data_specialist_output,
)
from app.services.sherlock_v3.tool_output import (
    build_call_name_index,
    is_tool_output_for,
)


def _tool_call(name: str, call_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        type='tool_call_item',
        raw_item={'name': name, 'call_id': call_id},
    )


def _tool_output(call_id: str, output: str) -> SimpleNamespace:
    return SimpleNamespace(
        type='tool_call_output_item',
        raw_item={'call_id': call_id},
        output=output,
    )


class ToolOutputMatcherTests(unittest.TestCase):
    def test_matcher_returns_false_on_unknown_call_id(self) -> None:
        # An output item whose call_id is not in the index never matches.
        index = build_call_name_index([_tool_call('submit_sql', 'c1')])
        orphan = _tool_output('c_unknown', '{"x": 1}')
        self.assertFalse(
            is_tool_output_for(orphan, 'submit_sql', call_name_index=index),
        )

    def test_matcher_matches_by_call_id_to_name(self) -> None:
        items = [
            _tool_call('submit_sql', 'c1'),
            _tool_output('c1', '{"x": 1}'),
        ]
        index = build_call_name_index(items)
        out = items[1]
        self.assertTrue(
            is_tool_output_for(out, 'submit_sql', call_name_index=index),
        )
        # Wrong name for the same call_id must not match.
        self.assertFalse(
            is_tool_output_for(out, 'other_tool', call_name_index=index),
        )

    def test_matcher_handles_attribute_style_raw_items(self) -> None:
        call = SimpleNamespace(
            type='tool_call_item',
            raw_item=SimpleNamespace(name='submit_sql', call_id='c1'),
        )
        out = SimpleNamespace(
            type='tool_call_output_item',
            raw_item=SimpleNamespace(call_id='c1'),
            output='{"x": 1}',
        )
        index = build_call_name_index([call, out])
        self.assertTrue(
            is_tool_output_for(out, 'submit_sql', call_name_index=index),
        )

    def test_non_tool_output_item_returns_false(self) -> None:
        index = build_call_name_index([])
        msg = SimpleNamespace(type='message_output_item')
        self.assertFalse(
            is_tool_output_for(msg, 'submit_sql', call_name_index=index),
        )


class DataExtractorNoLongerCatchAllTests(unittest.IsolatedAsyncioTestCase):
    async def test_data_extractor_no_longer_catch_all(self) -> None:
        # A tool output for a DIFFERENT tool name must NOT be mistaken for
        # submit_sql output. With the old True catch-all this leaked.
        run = SimpleNamespace(
            new_items=[
                _tool_call('some_other_tool', 'c1'),
                _tool_output('c1', '{"kind":"data","status":"ok"}'),
            ],
            final_output='clarify please',
        )
        result = await extract_data_specialist_output(run)
        # Falls back to final_output prose, NOT the other tool's payload.
        self.assertEqual(result, 'clarify please')

    async def test_data_extractor_matches_real_submit_sql_by_index(self) -> None:
        payload = json.dumps({'kind': 'data', 'status': 'ok', 'summary': 'ok'})
        run = SimpleNamespace(
            new_items=[
                _tool_call('submit_sql', 'c1'),
                _tool_output('c1', payload),
            ],
            final_output='ignored',
        )
        result = await extract_data_specialist_output(run)
        self.assertEqual(result, payload)


if __name__ == '__main__':
    unittest.main()
