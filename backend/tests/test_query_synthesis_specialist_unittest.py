"""Phase 3 — query_synthesis_specialist contract + extractor tests.

These tests do not spin up an actual Agents-SDK runner; they exercise
the synthesis brief contract (target gating, decomposition shape,
ambiguous follow-ups) and the ``custom_output_extractor`` factory that
re-validates the LLM's brief against the supervisor's runtime
toolbelt.
"""
from __future__ import annotations

import json
import unittest
from datetime import date
from typing import Any
from unittest.mock import MagicMock

from app.services.sherlock_v3.contracts import (
    SubQuestion,
    SynthesisBrief,
)
from app.services.sherlock_v3.query_synthesis_specialist import (
    build_query_synthesis_specialist,
    make_synthesis_output_extractor,
)


def _brief_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        'rewritten_question': 'Average rubric score by agent this week',
        'classification': 'answerable',
        'reason': 'single SQL aggregation; targets data_specialist',
        'suggested_followups': [],
        'available_targets': ['data_specialist'],
        'decomposition': [
            {
                'sub_question': 'Average rubric score per agent for the last 7 days',
                'target': 'data_specialist',
                'depends_on_sub_question': None,
            },
        ],
    }
    base.update(overrides)
    return base


class SynthesisBriefSelfContainedRewritesTests(unittest.TestCase):
    def test_answerable_brief_validates(self) -> None:
        brief = SynthesisBrief.model_validate_with_targets(
            _brief_dict(),
            available_targets=['data_specialist'],
        )
        self.assertEqual(brief.classification, 'answerable')
        self.assertEqual(len(brief.decomposition), 1)
        self.assertEqual(brief.decomposition[0].target, 'data_specialist')

    def test_empty_rewritten_question_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SynthesisBrief.model_validate_with_targets(
                _brief_dict(rewritten_question='   '),
                available_targets=['data_specialist'],
            )

    def test_answerable_with_empty_decomposition_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SynthesisBrief.model_validate_with_targets(
                _brief_dict(decomposition=[]),
                available_targets=['data_specialist'],
            )


class SynthesisBriefAmbiguousTests(unittest.TestCase):
    def test_ambiguous_requires_followups(self) -> None:
        with self.assertRaises(ValueError):
            SynthesisBrief.model_validate_with_targets(
                _brief_dict(
                    classification='ambiguous',
                    suggested_followups=[],
                    decomposition=[],
                ),
                available_targets=['data_specialist'],
            )

    def test_ambiguous_must_have_empty_decomposition(self) -> None:
        with self.assertRaises(ValueError):
            SynthesisBrief.model_validate_with_targets(
                _brief_dict(
                    classification='ambiguous',
                    suggested_followups=['Which agent?'],
                ),
                available_targets=['data_specialist'],
            )

    def test_ambiguous_with_followups_validates(self) -> None:
        brief = SynthesisBrief.model_validate_with_targets(
            _brief_dict(
                classification='ambiguous',
                suggested_followups=['Which agent are you asking about?'],
                decomposition=[],
            ),
            available_targets=['data_specialist'],
        )
        self.assertEqual(brief.classification, 'ambiguous')
        self.assertEqual(len(brief.suggested_followups), 1)


class SynthesisBriefTargetGatingTests(unittest.TestCase):
    def test_decomposition_targeting_unavailable_specialist_rejected(self) -> None:
        # authoring_specialist not available; brief targets it anyway.
        with self.assertRaises(ValueError):
            SynthesisBrief.model_validate_with_targets(
                _brief_dict(
                    decomposition=[
                        {
                            'sub_question': 'Draft an email',
                            'target': 'authoring_specialist',
                        },
                    ],
                ),
                available_targets=['data_specialist'],
            )

    def test_mixed_decomposition_with_authoring_available(self) -> None:
        # Mixed data+authoring decomposes correctly when authoring is wired.
        brief = SynthesisBrief.model_validate_with_targets(
            _brief_dict(
                rewritten_question=(
                    'List stuck leads and draft a follow-up email '
                    'for the top three'
                ),
                decomposition=[
                    {
                        'sub_question': 'List leads stuck > 7 days, top 50 by mql_score',
                        'target': 'data_specialist',
                    },
                    {
                        'sub_question': 'Draft a follow-up email for the top 3 leads',
                        'target': 'authoring_specialist',
                        'depends_on_sub_question': 0,
                    },
                ],
            ),
            available_targets=['data_specialist', 'authoring_specialist'],
        )
        self.assertEqual(brief.decomposition[1].target, 'authoring_specialist')
        self.assertEqual(brief.decomposition[1].depends_on_sub_question, 0)

    def test_runtime_available_targets_overrides_brief_field(self) -> None:
        # The LLM may have included ``authoring_specialist`` in
        # available_targets; the validator overwrites with runtime truth.
        brief = SynthesisBrief.model_validate_with_targets(
            _brief_dict(available_targets=['data_specialist', 'authoring_specialist']),
            available_targets=['data_specialist'],
        )
        self.assertEqual(brief.available_targets, ['data_specialist'])

    def test_depends_on_must_reference_earlier_sub_question(self) -> None:
        with self.assertRaises(ValueError):
            SynthesisBrief.model_validate_with_targets(
                _brief_dict(
                    decomposition=[
                        {
                            'sub_question': 'q1',
                            'target': 'data_specialist',
                            'depends_on_sub_question': 0,  # self-reference
                        },
                    ],
                ),
                available_targets=['data_specialist'],
            )


class SynthesisPromptTests(unittest.TestCase):
    def test_prompt_includes_current_date_for_relative_time(self) -> None:
        agent = build_query_synthesis_specialist(
            MagicMock(), 'inside-sales', model='gpt-4o-mini', available_targets=['data_specialist'],
        )
        prompt = agent.instructions
        assert isinstance(prompt, str)
        self.assertIn(f'CURRENT_DATE: {date.today().isoformat()}', prompt)

    def test_prompt_keeps_data_part_when_authoring_unavailable(self) -> None:
        agent = build_query_synthesis_specialist(
            MagicMock(), 'inside-sales', model='gpt-4o-mini', available_targets=['data_specialist'],
        )
        prompt = agent.instructions
        assert isinstance(prompt, str)
        # The collapsed authoring-routing rule keeps target gating intent.
        self.assertIn('Never name a target outside AVAILABLE_TARGETS', prompt)
        self.assertIn('data_specialist', prompt)


class SynthesisVocabularyGroundingTests(unittest.TestCase):
    """Step 1 — the planner is grounded with the data vocabulary."""

    _VOCAB = [
        {
            'name': 'fact_call_evaluation',
            'kind': 'table',
            'description': 'One row per evaluated call.',
            'synonyms': [],
        },
        {
            'name': 'rubric_score',
            'kind': 'metric',
            'description': 'Average rubric score for a call.',
            'synonyms': ['quality score', 'call score'],
        },
    ]

    def test_planner_receives_vocabulary(self) -> None:
        agent = build_query_synthesis_specialist(
            MagicMock(),
            'inside-sales',
            model='gpt-4o-mini',
            available_targets=['data_specialist'],
            vocabulary=self._VOCAB,
        )
        prompt = agent.instructions
        assert isinstance(prompt, str)
        # Names of real entities/metrics are present.
        self.assertIn('fact_call_evaluation', prompt)
        self.assertIn('rubric_score', prompt)
        # A synonym is rendered so the planner can map user phrasing.
        self.assertIn('quality score', prompt)

    def test_no_vocabulary_block_when_none(self) -> None:
        agent = build_query_synthesis_specialist(
            MagicMock(),
            'inside-sales',
            model='gpt-4o-mini',
            available_targets=['data_specialist'],
        )
        prompt = agent.instructions
        assert isinstance(prompt, str)
        # No vocabulary entries leak in when the app has no catalog.
        self.assertNotIn('fact_call_evaluation', prompt)
        self.assertNotIn('quality score', prompt)

    def test_planner_refuses_when_ungrounded(self) -> None:
        # Contract text: map words to real entities; refuse + ask ONE
        # clarifying question when a phrase can't be grounded.
        personality = build_query_synthesis_specialist(
            MagicMock(),
            'inside-sales',
            model='gpt-4o-mini',
            available_targets=['data_specialist'],
            vocabulary=self._VOCAB,
        ).instructions
        assert isinstance(personality, str)
        lowered = personality.lower()
        self.assertIn('cannot be grounded', lowered)
        self.assertIn('ambiguous', lowered)
        # One clarifying question — not a guessed field.
        self.assertIn('clarifying', lowered)

    def test_refusal_brief_yields_ambiguous(self) -> None:
        from app.services.sherlock_v3.query_synthesis_specialist import (
            _refusal_brief,
        )

        brief = _refusal_brief(
            rewritten_question='show me the thing',
            reason='phrase could not be grounded to the vocabulary',
            available_targets=['data_specialist'],
        )
        self.assertEqual(brief.classification, 'ambiguous')
        self.assertEqual(brief.decomposition, [])
        self.assertGreaterEqual(len(brief.suggested_followups), 1)


class SynthesisBriefNonDataTests(unittest.TestCase):
    def test_non_data_must_have_empty_decomposition(self) -> None:
        with self.assertRaises(ValueError):
            SynthesisBrief.model_validate_with_targets(
                _brief_dict(
                    classification='non_data',
                    suggested_followups=[],
                ),
                available_targets=['data_specialist'],
            )

    def test_non_data_valid_with_no_decomposition(self) -> None:
        brief = SynthesisBrief.model_validate_with_targets(
            _brief_dict(
                rewritten_question='Hello',
                classification='non_data',
                decomposition=[],
            ),
            available_targets=['data_specialist'],
        )
        self.assertEqual(brief.classification, 'non_data')


class SynthesisOutputExtractorTests(unittest.IsolatedAsyncioTestCase):
    """The extractor that the supervisor's ``as_tool`` call uses.

    It must:
      * pass through valid briefs as JSON;
      * substitute a refusal brief for malformed output (no silent fallback);
      * re-pin available_targets to the runtime truth.

    ``IsolatedAsyncioTestCase`` gives each test its own event loop, so
    these tests stay clean when batched with other async tests.
    """

    async def _run(self, extractor: Any, run_result: Any) -> dict[str, Any]:
        out = await extractor(run_result)
        return json.loads(out)

    async def test_extractor_passes_valid_synthesis_brief(self) -> None:
        extractor = make_synthesis_output_extractor(['data_specialist'])
        brief = SynthesisBrief.model_validate_with_targets(
            _brief_dict(),
            available_targets=['data_specialist'],
        )
        result = MagicMock()
        result.final_output = brief
        out = await self._run(extractor, result)
        self.assertEqual(out['classification'], 'answerable')
        self.assertEqual(out['available_targets'], ['data_specialist'])

    async def test_malformed_synthesis_output_produces_refusal(self) -> None:
        # Brief targets authoring_specialist but it's unavailable.
        extractor = make_synthesis_output_extractor(['data_specialist'])
        broken = _brief_dict(
            decomposition=[
                {'sub_question': 'do thing', 'target': 'authoring_specialist'},
            ],
        )
        result = MagicMock()
        result.final_output = broken
        out = await self._run(extractor, result)
        # Refusal brief carries classification='ambiguous' with reason.
        self.assertEqual(out['classification'], 'ambiguous')
        self.assertIn('authoring_specialist', out['reason'])
        # No silent fallback: decomposition is empty.
        self.assertEqual(out['decomposition'], [])

    async def test_non_json_string_output_produces_refusal(self) -> None:
        extractor = make_synthesis_output_extractor(['data_specialist'])
        result = MagicMock()
        result.final_output = 'not json'
        out = await self._run(extractor, result)
        self.assertEqual(out['classification'], 'ambiguous')

    async def test_missing_output_produces_refusal(self) -> None:
        extractor = make_synthesis_output_extractor(['data_specialist'])
        result = MagicMock()
        result.final_output = None
        out = await self._run(extractor, result)
        self.assertEqual(out['classification'], 'ambiguous')


class SubQuestionContractTests(unittest.TestCase):
    def test_sub_question_extra_forbidden(self) -> None:
        with self.assertRaises(Exception):
            SubQuestion.model_validate({
                'sub_question': 'q',
                'target': 'data_specialist',
                'unexpected_field': 'oops',
            })


if __name__ == '__main__':
    unittest.main()
