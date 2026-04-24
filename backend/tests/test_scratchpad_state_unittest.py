from __future__ import annotations

import unittest

from app.services.report_builder import scratchpad_state


class ScratchpadStateTests(unittest.TestCase):
    def test_build_previous_turn_context_returns_generic_summary(self):
        previous_turn = scratchpad_state.build_previous_turn_context(
            {
                'last_analysis': {
                    'question': 'Show rule violations across all evaluation runs',
                    'row_count': 11,
                    'columns': ['rule', 'violation_count'],
                    'chart_summary': {'kind': 'chart', 'mark': 'bar'},
                },
                'active_filters': {'status': 'VIOLATED'},
                'resolved_entities': {
                    'rule': {
                        'matches': [{'value': 'Food QnA Instructions'}],
                    }
                },
                'outcomes': [
                    {
                        'tool': 'data_query',
                        'artifact_type': 'chart',
                        'reason_code': None,
                        'counts': {'rows': 11, 'records': 0, 'affected': 0},
                    }
                ],
            }
        )

        self.assertEqual(previous_turn['user_goal'], 'Show rule violations across all evaluation runs')
        self.assertEqual(previous_turn['result_kind'], 'chart')
        self.assertEqual(previous_turn['result_status'], 'ok')
        self.assertEqual(previous_turn['recent_tools'], ['data_query'])
        self.assertEqual(previous_turn['active_filters']['status'], 'VIOLATED')
        self.assertEqual(previous_turn['active_entities']['rule'], ['Food QnA Instructions'])

    def test_build_analysis_snapshot_no_longer_emits_scope_recheck_hint(self):
        """M2: the app-alias / run_name scope-recheck band-aid is removed.

        Platform ontology now flags ``run_name`` as ``explicit_only`` in
        the scoped bundle, so the agent is told to resolve run identity
        through ``resolve_entity`` instead of silently fuzzy-matching.
        The old scratchpad post-hint is gone; this test locks that
        removal so the band-aid cannot sneak back.
        """
        snapshot = scratchpad_state.build_analysis_snapshot(
            {
                'question': 'Show kaira eval runs per status',
                'row_count': 0,
                'data': [],
                'typed_columns': [
                    {'name': 'status', 'role': 'dimension', 'data_type': 'nominal'},
                    {'name': 'total_runs', 'role': 'measure', 'data_type': 'quantitative'},
                ],
                'columns': [
                    {'name': 'status', 'role': 'dimension'},
                    {'name': 'total_runs', 'role': 'measure'},
                ],
                'applied_filters': {'run_name': 'kaira'},
            },
        )

        self.assertNotIn('scope_recheck_hint', snapshot)

        context = scratchpad_state.build_data_query_context(
            'show as pie',
            {
                'last_analysis': snapshot,
                'analysis_history': [],
                'active_filters': {'run_name': 'kaira'},
                'resolved_entities': {},
            },
        )

        self.assertIn('previous_turn', context)
        self.assertNotIn('scope_recheck_hint', context.get('prior_analysis', {}))


if __name__ == '__main__':
    unittest.main()
