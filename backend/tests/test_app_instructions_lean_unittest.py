"""S1-P-E — per-app business-semantics preamble cut.

The two-line boilerplate preamble ("Residual rules that the schema and
verified queries do not encode…") is pure framing the prompt assembly
already provides. Cut it from all three app files; keep every real rule.
"""
from __future__ import annotations

import unittest

from app.services.sherlock_v3.instructions import _load_app_default

_APPS = ('kaira-bot', 'voice-rx', 'inside-sales')


class AppInstructionsLeanTests(unittest.TestCase):
    def test_preamble_boilerplate_removed(self) -> None:
        for app_id in _APPS:
            block = _load_app_default(app_id)
            self.assertNotIn(
                'Residual rules that the schema and verified queries do not encode',
                block,
                f'{app_id}: boilerplate preamble not cut',
            )
            self.assertNotIn(
                'in addition to the safety contract',
                block,
                f'{app_id}: boilerplate preamble not cut',
            )

    def test_real_rules_survive(self) -> None:
        for app_id in _APPS:
            block = _load_app_default(app_id)
            self.assertIn(
                'one decimal place', block.lower(),
                f'{app_id}: load-bearing rule lost',
            )


if __name__ == '__main__':
    unittest.main()
