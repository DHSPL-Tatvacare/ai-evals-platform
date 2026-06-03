"""P5 — a failed submit_sql attempt renders the prior Verdict diagnostic as explicit retry corrections."""
from __future__ import annotations

import unittest

from app.services.sherlock_v3.contracts import Diagnostic, Verdict
from app.services.sherlock_v3.data_specialist import _render_retry_corrections


class RetryCorrectionsRenderTests(unittest.TestCase):
    def _verdict(self, **diag_kwargs) -> Verdict:
        base = dict(
            rule_id='R7',
            rule_number=7,
            rule_name='Scope predicates',
            message='alias e is not filtered on :tenant_id and :app_id',
        )
        base.update(diag_kwargs)
        return Verdict(status='invalid', diagnostic=Diagnostic(**base))

    def test_render_contains_rule_id_and_hint(self) -> None:
        verdict = self._verdict(
            hint='filter every joined alias on :tenant_id and :app_id',
        )
        rendered = _render_retry_corrections(verdict)
        self.assertIn('R7', rendered)
        self.assertIn('filter every joined alias on :tenant_id and :app_id', rendered)
        self.assertIn('alias e is not filtered', rendered)

    def test_render_lists_required_scope_predicates(self) -> None:
        verdict = self._verdict(
            required_scope_predicates=['e.tenant_id = :tenant_id', 'e.app_id = :app_id'],
        )
        rendered = _render_retry_corrections(verdict)
        self.assertIn('e.tenant_id = :tenant_id', rendered)
        self.assertIn('e.app_id = :app_id', rendered)

    def test_render_surfaces_did_you_mean(self) -> None:
        verdict = self._verdict(
            rule_id='R3',
            did_you_mean={'evaluaton_runs': 'evaluation_runs'},
        )
        rendered = _render_retry_corrections(verdict)
        self.assertIn('evaluaton_runs', rendered)
        self.assertIn('evaluation_runs', rendered)

    def test_render_handles_missing_diagnostic(self) -> None:
        verdict = Verdict(status='invalid', diagnostic=None)
        rendered = _render_retry_corrections(verdict)
        self.assertTrue(rendered)


class BouncerRejectionSummaryFeedsDiagnosticTests(unittest.TestCase):
    """The LLM-facing summary on a bouncer rejection IS the retry context; it must carry the diagnostic."""

    def test_bouncer_summary_renders_full_corrections(self) -> None:
        from app.services.sherlock_v3.data_specialist import _bouncer_summary

        verdict = Verdict(
            status='invalid',
            diagnostic=Diagnostic(
                rule_id='R7',
                rule_number=7,
                rule_name='Scope predicates',
                message='alias e is not filtered on :tenant_id and :app_id',
                hint='filter every joined alias',
                required_scope_predicates=['e.tenant_id = :tenant_id'],
            ),
        )
        summary = _bouncer_summary(verdict)
        self.assertIn('R7', summary)
        self.assertIn('filter every joined alias', summary)
        self.assertIn('e.tenant_id = :tenant_id', summary)


if __name__ == '__main__':
    unittest.main()
