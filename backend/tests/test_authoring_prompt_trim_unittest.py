"""S1-P-D — authoring_specialist._build_system_prompt prose trim.

Asserts the trimmed prose keeps the CanvasPatch contract + every
reason-code the handlers still raise + the sink.complete placeholder
rule + "never claim saved", drops the node-taxonomy tutorial and the
dead view='view' defensive paragraph, and preserves static-first
ordering (the Goal prose precedes the per-turn {snapshot} injection).
"""
from __future__ import annotations

import unittest
import uuid

from app.services.orchestration_authoring.builder_snapshot import BuilderSnapshot
from app.services.sherlock_v3 import authoring_specialist as auth_mod


def _stub_snapshot() -> BuilderSnapshot:
    return BuilderSnapshot(
        workflow_id=uuid.uuid4(),
        version_id=None,
        workflow_type='crm',
        app_id='inside-sales',
        definition={'nodes': [{'id': 'n1', 'node_type': 'sink.complete'}], 'edges': []},
        data_hash='hash-1',
        view_mode='edit',
    )


def _prompt() -> str:
    return auth_mod._build_system_prompt(
        app_id='inside-sales', builder_context=_stub_snapshot(),
    )


class AuthoringPromptTrimTests(unittest.TestCase):
    def test_keeps_contract_tokens(self) -> None:
        prompt = _prompt()
        for token in (
            'apply_patch',
            'CanvasPatch',
            'UUID_NOT_AUTHORIZED',
            'UNKNOWN_OUTCOME',
            'UNKNOWN_EVENT',
            'NODE_CONFIG_INVALID',
            'sink.complete',
        ):
            self.assertIn(token, prompt, f'missing contract token: {token}')

    def test_keeps_schema_is_contract_rule(self) -> None:
        prompt = _prompt()
        self.assertIn('THIS IS THE CONTRACT', prompt)

    def test_keeps_never_claim_saved_rule(self) -> None:
        prompt = _prompt()
        lowered = prompt.lower()
        self.assertIn('saved', lowered)
        self.assertIn('published', lowered)

    def test_drops_node_taxonomy_tutorial(self) -> None:
        # The {node_schemas} block already carries [category=…, outputs=…];
        # the prose lecture re-teaching the taxonomy is cut. The sink.complete
        # placeholder rule survives (asserted above).
        prompt = _prompt()
        self.assertNotIn('Choosing the right node', prompt)
        self.assertNotIn('fans out by branch', prompt)
        self.assertNotIn('Sources (`source.*`) START', prompt)

    def test_drops_dead_view_mode_paragraph(self) -> None:
        # The supervisor only builds this agent in edit mode; the defensive
        # "if you somehow see 'view'" branch is dead.
        prompt = _prompt()
        self.assertNotIn('somehow see', prompt)

    def test_static_first_ordering(self) -> None:
        prompt = _prompt()
        # The Goal prose precedes the per-turn snapshot injection.
        self.assertLess(prompt.index('# Goal'), prompt.index('# Canvas snapshot'))


if __name__ == '__main__':
    unittest.main()
