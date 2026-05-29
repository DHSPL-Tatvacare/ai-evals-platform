"""Null-key regression tests for ``DistributionSeries``.

The kaira cross-run aggregator consumes ``series.key`` raw via
``series.key.startswith('goal:')`` (canonical_adapters.py). Persisted report
artifacts serialize the ``key`` field even when it is unset, so a cached series
can arrive as ``{"key": null, ...}``. Before the contract-boundary fix that
crashed every consumer with ``AttributeError: 'NoneType' object has no
attribute 'startswith'``.

These tests pin the fix at the contract boundary:

* a ``DistributionSeries`` whose ``key`` is explicitly ``None`` validates and
  coerces to ``''`` (a no-op for ``.startswith`` checks), and
* the cross-run kaira adapter path does not raise when a run carries a
  ``kaira-distributions`` section whose series have ``key: null``.
"""

from __future__ import annotations

import unittest


class DistributionSeriesNullKeyTests(unittest.TestCase):
    def test_explicit_none_key_coerced_to_empty_string(self):
        from app.services.reports.contracts.report_sections import DistributionSeries

        series = DistributionSeries.model_validate(
            {'key': None, 'label': 'Adversarial', 'categories': ['passRate'], 'values': [75.0]}
        )
        self.assertEqual(series.key, '')

    def test_coerced_key_supports_raw_startswith(self):
        # The adapter calls series.key.startswith('goal:') directly; with the
        # coercion that is safe even when the persisted key was null.
        from app.services.reports.contracts.report_sections import DistributionSeries

        series = DistributionSeries.model_validate(
            {'key': None, 'label': 'Adversarial', 'categories': ['passRate'], 'values': [75.0]}
        )
        self.assertFalse(series.key.startswith('goal:'))


class KairaCrossRunNullKeyTests(unittest.TestCase):
    """adapt_kaira_cross_run_from_runs must not raise when a distributions series carries key: null."""

    def _kaira_analytics_config(self):
        from app.schemas.app_config import AppConfig
        from app.services.seed_defaults import APP_SEEDS

        for seed in APP_SEEDS:
            if seed['slug'] == 'kaira-bot':
                return AppConfig.model_validate(seed['config']).analytics
        raise KeyError('kaira-bot')

    def _run_payload_with_null_key_series(self, run_name: str, health: float) -> dict:
        # Mirrors the single-run adapter / cached-artifact shape, but the first
        # distributions series carries an explicit null key (as persisted JSON
        # would round-trip an unset key field).
        return {
            'schemaVersion': 'v1',
            'metadata': {
                'appId': 'kaira-bot',
                'runId': run_name,
                'runName': run_name,
                'evalType': 'batch_thread',
                'createdAt': '2026-03-01T00:00:00+00:00',
                'computedAt': '2026-03-01T00:05:00+00:00',
            },
            'sections': [
                {
                    'id': 'kaira-summary',
                    'type': 'summary_cards',
                    'title': 'Summary',
                    'data': [
                        {'key': 'health-score', 'label': 'Health Score', 'value': f'{health:.1f}', 'tone': 'positive'},
                        {'key': 'total', 'label': 'Total Threads', 'value': '10', 'tone': 'neutral'},
                    ],
                },
                {
                    'id': 'kaira-distributions',
                    'type': 'distribution_chart',
                    'title': 'Goal Distributions',
                    'data': [
                        # Persisted with an explicit null key — the crash case.
                        {'key': None, 'label': 'Adversarial', 'categories': ['passRate'], 'values': [health]},
                        {'key': 'goal:medication_adherence', 'label': 'Medication Adherence', 'categories': ['passRate'], 'values': [health - 5]},
                    ],
                },
            ],
            'exportDocument': {
                'schemaVersion': 'v1',
                'title': run_name,
                'theme': {
                    'accent': '#0f766e',
                    'accentMuted': '#99f6e4',
                    'border': '#d1d5db',
                    'textPrimary': '#0f172a',
                    'textSecondary': '#475569',
                    'background': '#ffffff',
                },
                'blocks': [{'id': 'cover', 'type': 'cover', 'title': run_name}],
            },
        }

    def test_cross_run_does_not_raise_with_null_key_series(self):
        from app.services.reports.canonical_adapters import adapt_kaira_cross_run_from_runs

        runs_data = [
            ({'id': 'run-1', 'created_at': '2026-03-01T00:00:00+00:00'},
             self._run_payload_with_null_key_series('Run 1', 82.0)),
            ({'id': 'run-2', 'created_at': '2026-03-02T00:00:00+00:00'},
             self._run_payload_with_null_key_series('Run 2', 76.0)),
        ]
        report = adapt_kaira_cross_run_from_runs(
            runs_data, self._kaira_analytics_config(), app_id='kaira-bot', total_runs_available=2
        )
        self.assertIsNotNone(report)


if __name__ == '__main__':
    unittest.main()
