"""Step 1 — build_data_specialist must merge grounding.verified_examples
into the SAME exemplars arg of build_data_specialist_prompt (dynamic first,
deduped), without adding a second prompt block.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.sherlock_v3 import data_specialist as ds_mod
from app.services.sherlock_v3.grounding import GroundingContext, VerifiedExampleRef


_STATIC_EXEMPLARS = [
    {'question': 'How many calls today?', 'sql': 'SELECT count(*) FROM calls'},
]


class VerifiedExamplesMergeTests(unittest.TestCase):
    def _build(self, grounding: GroundingContext | None):
        captured: dict = {}

        def _fake_prompt(*, exemplars, **_kwargs):
            captured['exemplars'] = exemplars
            return 'PROMPT'

        with patch.object(
            ds_mod, 'build_data_specialist', wraps=ds_mod.build_data_specialist
        ):
            with patch(
                'app.services.chat_engine.workbench_catalog.load_workbench_catalog_strict',
                return_value=object(),
            ), patch(
                'app.services.chat_engine.workbench_catalog.workbench_to_prompt_inputs',
                return_value=({}, [], [], list(_STATIC_EXEMPLARS)),
            ), patch.object(
                ds_mod, 'build_data_specialist_prompt', side_effect=_fake_prompt
            ), patch.object(
                ds_mod, 'make_specialist_agent', return_value=object()
            ):
                ds_mod.build_data_specialist(
                    client=object(),  # type: ignore[arg-type]
                    app_id='voice-rx',
                    model='gpt-4o',
                    grounding=grounding,
                )
        return captured['exemplars']

    def test_verified_examples_merged_dynamic_first(self) -> None:
        grounding = GroundingContext(
            app_id='voice-rx',
            user_message='pass rate trend',
            verified_examples=(
                VerifiedExampleRef(
                    id='v1',
                    question='Weekly pass rate trend?',
                    sql='SELECT week, avg(pass) FROM evals GROUP BY week',
                    score=0.9,
                    source='thumbs_up',
                ),
            ),
        )
        merged = self._build(grounding)
        # dynamic verified example first
        self.assertEqual(merged[0]['question'], 'Weekly pass rate trend?')
        self.assertEqual(
            merged[0]['sql'], 'SELECT week, avg(pass) FROM evals GROUP BY week'
        )
        # static catalog exemplar retained
        self.assertIn(_STATIC_EXEMPLARS[0], merged)

    def test_merge_dedupes_overlapping_pairs(self) -> None:
        grounding = GroundingContext(
            app_id='voice-rx',
            user_message='dup',
            verified_examples=(
                VerifiedExampleRef(
                    id='dup',
                    question=_STATIC_EXEMPLARS[0]['question'],
                    sql=_STATIC_EXEMPLARS[0]['sql'],
                    score=0.8,
                    source='thumbs_up',
                ),
            ),
        )
        merged = self._build(grounding)
        pairs = [(m['question'], m['sql']) for m in merged]
        self.assertEqual(len(pairs), len(set(pairs)), 'merge must dedupe by (question, sql)')

    def test_merge_caps_total(self) -> None:
        many = tuple(
            VerifiedExampleRef(
                id=f'v{i}', question=f'q{i}', sql=f'SELECT {i}', score=0.5, source='thumbs_up'
            )
            for i in range(20)
        )
        grounding = GroundingContext(
            app_id='voice-rx', user_message='many', verified_examples=many
        )
        merged = self._build(grounding)
        self.assertLessEqual(len(merged), 10)

    def test_no_grounding_uses_static_only(self) -> None:
        merged = self._build(None)
        self.assertEqual(merged, _STATIC_EXEMPLARS)


class SinglePromptBlockTests(unittest.TestCase):
    """The merge feeds the existing exemplars arg — exactly ONE
    'VERIFIED QUERY EXAMPLES' header is rendered, not a second block."""

    def test_data_prompt_includes_retrieved_examples_one_header(self) -> None:
        from app.services.chat_engine.workbench_catalog import (
            load_workbench_catalog_strict,
            workbench_to_prompt_inputs,
        )
        from app.services.sherlock_v3.data_specialist import build_data_specialist_prompt

        catalog = load_workbench_catalog_strict('voice-rx')
        schema_context, allowed_tables, role_hints, static = (
            workbench_to_prompt_inputs(catalog)
        )
        retrieved = {
            'question': 'Distinct evaluator question XYZ?',
            'sql': 'SELECT distinct_evaluator_marker FROM evals',
        }
        merged = [retrieved, *static]
        prompt = build_data_specialist_prompt(
            app_id='voice-rx',
            schema_context=schema_context,
            allowed_tables=allowed_tables,
            column_role_hints=role_hints,
            exemplars=merged,
            max_rows=1000,
        )
        self.assertIn('Distinct evaluator question XYZ?', prompt)
        self.assertIn('SELECT distinct_evaluator_marker FROM evals', prompt)
        self.assertEqual(prompt.count('VERIFIED QUERY EXAMPLES'), 1)


if __name__ == '__main__':
    unittest.main()
