"""S1-3 — uniform refusal/summary contract.

Invariant: no ``SubtaskResult`` with ``status in {'error','empty'}`` may
carry an empty ``summary``. The summary always carries the specialist's
human-readable reason so the FE error card is never blank.
"""
from __future__ import annotations

import unittest

from app.services.sherlock_v3.contracts.brief import Attempt
from app.services.sherlock_v3.contracts.bouncer import Verdict
from app.services.sherlock_v3.contracts.result import SpecialistResult
from app.services.sherlock_v3.subtask_result import project_specialist_output


def _data_result_json(*, status: str, summary: str, attempts=None) -> str:
    return SpecialistResult(
        kind='data' if status != 'error' else 'error',
        status=status,
        summary=summary,
        attempts=attempts or [],
    ).model_dump_json()


class RefusalSummaryContractTests(unittest.TestCase):
    def test_unparseable_data_output_has_nonempty_summary(self) -> None:
        result, is_error = project_specialist_output('data_specialist', '')
        self.assertTrue(is_error)
        self.assertEqual(result.status, 'error')
        self.assertNotEqual(result.summary, '')

    def test_unparseable_data_garbage_has_nonempty_summary(self) -> None:
        result, is_error = project_specialist_output('data_specialist', 'not json {')
        self.assertTrue(is_error)
        self.assertEqual(result.status, 'error')
        self.assertNotEqual(result.summary, '')

    def test_empty_text_specialist_has_nonempty_summary(self) -> None:
        result, is_error = project_specialist_output('authoring_specialist', '')
        self.assertFalse(is_error)
        self.assertEqual(result.status, 'empty')
        self.assertNotEqual(result.summary, '')

    def test_ok_text_specialist_may_have_empty_summary(self) -> None:
        # The invariant binds only error|empty; on ok the supervisor reads
        # the text directly, so an empty summary stays acceptable.
        result, is_error = project_specialist_output(
            'authoring_specialist', 'Here is the narrative.',
        )
        self.assertFalse(is_error)
        self.assertEqual(result.status, 'ok')

    def test_invariant_no_empty_summary_on_error_or_empty(self) -> None:
        ok_attempt = [
            Attempt(sql='SELECT 1', verdict=Verdict(status='ok'), status='ok', row_count=1),
        ]
        cases = [
            ('data_specialist', ''),
            ('data_specialist', 'not json {'),
            ('data_specialist', _data_result_json(status='error', summary='bouncer refused')),
            ('data_specialist', _data_result_json(status='ok', summary='12 rows', attempts=ok_attempt)),
            ('authoring_specialist', ''),
            ('authoring_specialist', '   '),
            ('authoring_specialist', 'A real narrative answer.'),
            ('query_synthesis_specialist', ''),
            ('query_synthesis_specialist', '   '),
            ('query_synthesis_specialist', 'synthesized brief text'),
        ]
        for specialist, output in cases:
            result, _ = project_specialist_output(specialist, output)
            with self.subTest(specialist=specialist, output=output[:20]):
                self.assertFalse(
                    result.status in {'error', 'empty'} and result.summary == '',
                    f'{specialist} produced {result.status} with empty summary',
                )


if __name__ == '__main__':
    unittest.main()
