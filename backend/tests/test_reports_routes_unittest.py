import os
import sys
import unittest

from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.reports.cache_validation import (
    load_cached_payload_or_raise,
    partition_valid_single_run_payloads,
)
from app.services.reports.contracts.run_report import PlatformRunReportPayload


def _valid_run_payload() -> dict:
    return {
        'schemaVersion': 'v1',
        'metadata': {
            'appId': 'inside-sales',
            'runId': 'run-123',
            'runName': 'Inside Sales Batch',
            'evalType': 'call_quality',
            'createdAt': '2026-04-01T10:00:00+00:00',
            'computedAt': '2026-04-01T10:05:00+00:00',
        },
        'sections': [
            {
                'id': 'inside-sales-summary',
                'type': 'summary_cards',
                'title': 'Summary',
                'variant': 'overview',
                'data': [
                    {'key': 'avg-qa-score', 'label': 'Average QA Score', 'value': '91', 'tone': 'positive'},
                ],
            },
        ],
        'exportDocument': {
            'schemaVersion': 'v1',
            'title': 'Inside Sales Batch',
            'theme': {
                'accent': '#1d4ed8',
                'accentMuted': '#dbeafe',
                'border': '#cbd5e1',
                'textPrimary': '#0f172a',
                'textSecondary': '#475569',
                'background': '#ffffff',
            },
            'blocks': [
                {'id': 'cover', 'type': 'cover', 'title': 'Inside Sales Batch', 'subtitle': 'Single-run report', 'metadata': {}},
            ],
        },
    }


def _legacy_run_payload() -> dict:
    return {
        'metadata': {
            'appId': 'inside-sales',
            'runId': 'run-legacy',
            'runName': 'Legacy Inside Sales Batch',
            'evalType': 'call_quality',
            'createdAt': '2026-04-01T10:00:00+00:00',
        },
        'runSummary': {
            'totalCalls': 5,
            'evaluatedCalls': 5,
            'avgQaScore': 91,
            'avgCompliancePassRate': 1,
        },
    }


class ReportsRouteHelperTests(unittest.TestCase):
    def test_load_cached_payload_or_raise_accepts_canonical_run_payload(self):
        payload = load_cached_payload_or_raise(
            PlatformRunReportPayload.model_validate,
            _valid_run_payload(),
            detail='should not fail',
            log_message='test log',
        )

        self.assertEqual(payload.metadata.computed_at, '2026-04-01T10:05:00+00:00')
        self.assertEqual(payload.sections[0].id, 'inside-sales-summary')

    def test_load_cached_payload_or_raise_converts_validation_error_to_conflict(self):
        with self.assertRaises(HTTPException) as ctx:
            load_cached_payload_or_raise(
                PlatformRunReportPayload.model_validate,
                _legacy_run_payload(),
                detail='Cached report is outdated. Regenerate the report.',
                log_message='test log',
            )

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, 'Cached report is outdated. Regenerate the report.')

    def test_partition_valid_single_run_payloads_skips_legacy_rows(self):
        valid_rows, invalid_count = partition_valid_single_run_payloads(
            [
                ({'id': 'run-valid'}, _valid_run_payload()),
                ({'id': 'run-legacy'}, _legacy_run_payload()),
            ],
            PlatformRunReportPayload,
        )

        self.assertEqual(invalid_count, 1)
        self.assertEqual(len(valid_rows), 1)
        self.assertEqual(valid_rows[0][0]['id'], 'run-valid')
        self.assertIn('computedAt', valid_rows[0][1]['metadata'])
