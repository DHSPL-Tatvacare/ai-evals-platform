from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.chat_engine import catalog_tools


class _Result:
    def __init__(self, *, rows=None):
        self._rows = rows or []

    def all(self):
        return list(self._rows)


class CatalogToolsTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_column_comment_extracts_structured_metadata(self):
        parsed = catalog_tools.parse_column_comment(
            'Type of evaluation. Role: dimension. Values: batch_thread, call_quality. '
            'Synonyms: evaluation type, run type. Unit: percent. Ordering: PASS, FAIL. Pre-aggregated.'
        )

        self.assertEqual(parsed['description'], 'Type of evaluation')
        self.assertEqual(parsed['role'], 'dimension')
        self.assertEqual(parsed['values'], ['batch_thread', 'call_quality'])
        self.assertEqual(parsed['synonyms'], ['evaluation type', 'run type'])
        self.assertEqual(parsed['unit'], 'percent')
        self.assertEqual(parsed['ordering'], ['PASS', 'FAIL'])
        self.assertTrue(parsed['pre_aggregated'])

    def test_parse_column_comment_tolerates_missing_fields(self):
        parsed = catalog_tools.parse_column_comment('Run metadata only.')

        self.assertEqual(parsed['description'], 'Run metadata only')
        self.assertIsNone(parsed['role'])
        self.assertEqual(parsed['values'], [])
        self.assertFalse(parsed['pre_aggregated'])

    def test_detect_jsonb_structure_finds_nested_arrays_and_leaf_samples(self):
        structure, sample_values = catalog_tools.detect_jsonb_structure(
            [
                {
                    'entities': {
                        'leads': [
                            {'name': 'Rajesh Kumar', 'follow_up_date': '2026-04-01'},
                            {'name': 'Priya Shah', 'follow_up_date': '2026-04-02'},
                        ],
                    },
                    'summary': 'ready',
                },
                {
                    'entities': {
                        'leads': [
                            {'name': 'Amit Patel', 'follow_up_date': '2026-04-03'},
                        ],
                    },
                    'summary': 'pending',
                },
            ]
        )

        self.assertEqual(structure['entities']['leads'][0]['name'], 'text')
        self.assertEqual(structure['entities']['leads'][0]['follow_up_date'], 'date')
        self.assertEqual(structure['summary'], 'text')
        self.assertEqual(
            sample_values['entities.leads[0].name'],
            ['Rajesh Kumar', 'Priya Shah', 'Amit Patel'],
        )

    async def test_catalog_inspect_parses_comments_and_marks_jsonb_columns(self):
        db = AsyncMock()
        db.execute.side_effect = [
            _Result(rows=[
                ('eval_type', 'text', 'text', 'NO', None, 'Type of evaluation. Role: dimension. Values: batch_thread, call_quality.'),
                ('context', 'jsonb', 'jsonb', 'YES', None, 'App metadata. Role: dimension.'),
            ]),
            _Result(rows=[('eval_type',)]),
            _Result(rows=[('idx_eval_type', 'CREATE INDEX idx_eval_type ON analytics_run_facts (eval_type)')]),
        ]

        envelope = await catalog_tools.catalog_inspect(
            table='analytics_run_facts',
            column=None,
            db=db,
            auth=SimpleNamespace(),
            app_id='inside-sales',
            app_config={},
            semantic_model={'tables': {'analytics_run_facts': {}}},
        )

        # Phase 2: catalog tools return §6.2 envelopes directly.
        self.assertEqual(envelope['status'], 'ok')
        self.assertEqual(envelope['outcome']['kind'], 'read')
        self.assertEqual(envelope['outcome']['capability'], 'analytics')
        payload = envelope['payload']
        self.assertEqual(payload['primary_key'], ['eval_type'])
        self.assertEqual(payload['columns'][0]['comment_metadata']['role'], 'dimension')
        self.assertTrue(payload['columns'][1]['is_jsonb'])
        self.assertEqual(payload['columns'][1]['sample_hint'], 'use catalog_sample to inspect structure')

    async def test_catalog_values_scopes_rows_by_tenant_and_app(self):
        captured = {}
        auth = SimpleNamespace(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            is_owner=True,
            app_access=frozenset({'inside-sales'}),
        )
        db = AsyncMock()

        async def _execute(query):
            captured['query'] = str(query)
            return _Result(rows=[('PASS', 7)])

        db.execute.side_effect = _execute

        envelope = await catalog_tools.catalog_values(
            table='analytics_eval_facts',
            column='result_status',
            search='pa',
            db=db,
            auth=auth,
            app_id='inside-sales',
            app_config={},
            semantic_model={'tables': {'analytics_eval_facts': {}}},
        )

        self.assertEqual(envelope['status'], 'ok')
        self.assertEqual(envelope['outcome']['kind'], 'read')
        self.assertEqual(envelope['payload']['values'][0]['value'], 'PASS')
        self.assertIn('analytics_eval_facts.tenant_id', captured['query'])
        self.assertIn('analytics_eval_facts.app_id', captured['query'])

    async def test_catalog_values_rejects_disallowed_tables(self):
        db = AsyncMock()

        envelope = await catalog_tools.catalog_values(
            table='users',
            column='email',
            db=db,
            auth=SimpleNamespace(),
            app_id='inside-sales',
            app_config={},
            semantic_model={'tables': {'analytics_eval_facts': {}}},
        )

        self.assertEqual(envelope['status'], 'error')
        self.assertEqual(envelope['outcome']['kind'], 'error')
        self.assertEqual(envelope['outcome']['reason_code'], 'ENTITY_OUT_OF_SCOPE')
        self.assertTrue(
            any('not declared in the manifest' in w for w in envelope['outcome']['warnings']),
            envelope['outcome']['warnings'],
        )
        db.execute.assert_not_called()

    async def test_catalog_inspect_rejects_missing_app_access(self):
        db = AsyncMock()

        envelope = await catalog_tools.catalog_inspect(
            table='analytics_run_facts',
            column=None,
            db=db,
            auth=SimpleNamespace(is_owner=False, app_access=frozenset()),
            app_id='inside-sales',
            app_config={},
            semantic_model={'tables': {'analytics_run_facts': {}}},
        )

        self.assertEqual(envelope['status'], 'error')
        self.assertEqual(envelope['outcome']['reason_code'], 'PERMISSION_DENIED')
        self.assertTrue(
            any('App access denied' in w for w in envelope['outcome']['warnings']),
            envelope['outcome']['warnings'],
        )
        db.execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
