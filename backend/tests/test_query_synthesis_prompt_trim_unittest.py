"""S1-P-C — query_synthesis_specialist prompt trim.

Asserts the trimmed `_PERSONALITY` (+ assembled prompt) keeps the
SynthesisBrief/SubQuestion contract tokens, the two safety rules
("never name a target outside AVAILABLE_TARGETS", "never invent data
values"), collapses the three authoring-routing bullets into ONE rule,
and preserves static-first ordering (static `_PERSONALITY` precedes the
injected CURRENT_DATE / AVAILABLE_TARGETS block).
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.services.sherlock_v3 import query_synthesis_specialist as qs_mod


def _assembled_prompt() -> str:
    agent = qs_mod.build_query_synthesis_specialist(
        MagicMock(),
        'inside-sales',
        model='gpt-4o-mini',
        available_targets=['data_specialist', 'authoring_specialist'],
    )
    return agent.instructions


class QuerySynthesisPromptTrimTests(unittest.TestCase):
    def test_keeps_contract_tokens(self) -> None:
        prompt = _assembled_prompt()
        for token in (
            'SynthesisBrief',
            'rewritten_question',
            'classification',
            'decomposition',
            'depends_on_sub_question',
            'AVAILABLE_TARGETS',
            'SubQuestion',
        ):
            self.assertIn(token, prompt, f'missing contract token: {token}')

    def test_keeps_safety_rules(self) -> None:
        personality = qs_mod._PERSONALITY
        self.assertIn('never name a target outside', personality.lower())
        self.assertIn('never invent data values', personality.lower())

    def test_authoring_routing_collapsed_to_one_rule(self) -> None:
        # The three near-duplicate authoring-routing branches collapse into a
        # single rule; the extractor enforces target validity structurally, so
        # the prompt only needs intent. Pin that the verbose branches are gone.
        personality = qs_mod._PERSONALITY
        self.assertNotIn('decompose into TWO sub-questions', personality)
        self.assertNotIn('the user asks for both', personality)
        self.assertNotIn('the user asks only for', personality)

    def test_static_first_ordering(self) -> None:
        prompt = _assembled_prompt()
        # Static personality prose precedes the per-turn injections.
        self.assertLess(prompt.index('SynthesisBrief'), prompt.index('CURRENT_DATE'))
        self.assertLess(prompt.index('SynthesisBrief'), prompt.index('AVAILABLE_TARGETS: ['))


if __name__ == '__main__':
    unittest.main()
