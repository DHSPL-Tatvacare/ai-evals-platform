"""unittest coverage for pure cross-run aggregators."""

import importlib.util
import os
import unittest


def _load_module(name: str, relative_path: str):
    path = os.path.join(os.path.dirname(__file__), '..', 'app', 'services', 'reports', relative_path)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cross_run_mod = _load_module('cross_run_aggregator', 'cross_run_aggregator.py')
inside_sales_mod = _load_module('inside_sales_cross_run', 'inside_sales_cross_run.py')

CrossRunAggregator = cross_run_mod.CrossRunAggregator
InsideSalesCrossRunAggregator = inside_sales_mod.InsideSalesCrossRunAggregator


class KairaCrossRunAggregatorTests(unittest.TestCase):
    def test_aggregate_builds_health_and_issue_rollups(self):
        runs_data = [
            (
                {
                    'id': 'run-1',
                    'eval_type': 'batch_thread',
                    'created_at': '2026-03-01T00:00:00+00:00',
                    'batch_metadata': {'name': 'Run 1'},
                },
                {
                    'metadata': {'totalThreads': 10},
                    'healthScore': {
                        'numeric': 82,
                        'grade': 'B+',
                        'breakdown': {
                            'intentAccuracy': {'value': 80},
                            'correctnessRate': {'value': 84},
                        },
                    },
                    'ruleCompliance': {
                        'rules': [
                            {'ruleId': 'rule-a', 'section': 'Intent', 'rate': 0.7, 'severity': 'HIGH'},
                        ],
                    },
                    'narrative': {
                        'topIssues': [
                            {'rank': 1, 'area': 'Intent', 'description': 'Intent slips', 'affectedCount': 3},
                        ],
                        'recommendations': [
                            {'priority': 'P0', 'area': 'Intent', 'action': 'Tighten routing', 'estimatedImpact': '-3 intent failures'},
                        ],
                    },
                },
            ),
            (
                {
                    'id': 'run-2',
                    'eval_type': 'batch_thread',
                    'created_at': '2026-03-02T00:00:00+00:00',
                    'batch_metadata': {'name': 'Run 2'},
                },
                {
                    'metadata': {'totalThreads': 8},
                    'healthScore': {
                        'numeric': 76,
                        'grade': 'B',
                        'breakdown': {
                            'intentAccuracy': {'value': 74},
                            'correctnessRate': {'value': 78},
                        },
                    },
                    'ruleCompliance': {
                        'rules': [
                            {'ruleId': 'rule-a', 'section': 'Intent', 'rate': 0.6, 'severity': 'HIGH'},
                        ],
                    },
                    'narrative': {
                        'topIssues': [
                            {'rank': 2, 'area': 'Intent', 'description': 'Intent slips again', 'affectedCount': 2},
                        ],
                        'recommendations': [
                            {'priority': 'P1', 'area': 'Intent', 'action': 'Retune prompt', 'estimatedImpact': '-2 intent failures'},
                        ],
                    },
                },
            ),
        ]

        analytics = CrossRunAggregator(runs_data, 3).aggregate()

        self.assertEqual(analytics.stats.total_runs, 2)
        self.assertEqual(analytics.stats.all_runs, 3)
        self.assertEqual(analytics.stats.total_threads, 18)
        self.assertAlmostEqual(analytics.stats.avg_health_score, 79.0)
        self.assertEqual(analytics.rule_compliance_heatmap.rows[0].rule_id, 'rule-a')
        self.assertEqual(analytics.issues_and_recommendations.runs_with_narrative, 2)
        self.assertGreaterEqual(len(analytics.issues_and_recommendations.issues), 1)


class InsideSalesCrossRunAggregatorTests(unittest.TestCase):
    def test_aggregate_builds_dimension_compliance_and_flag_rollups(self):
        runs_data = [
            (
                {
                    'id': 'sales-1',
                    'created_at': '2026-03-01T00:00:00+00:00',
                    'batch_metadata': {'run_name': 'Sales Run 1'},
                },
                {
                    'metadata': {'runName': 'Sales Run 1'},
                    'runSummary': {
                        'totalCalls': 12,
                        'evaluatedCalls': 10,
                        'avgQaScore': 81,
                        'compliancePassRate': 90,
                    },
                    'dimensionBreakdown': {
                        'discovery': {
                            'label': 'Discovery',
                            'avg': 78,
                            'maxPossible': 100,
                            'greenThreshold': 80,
                            'yellowThreshold': 60,
                        },
                    },
                    'complianceBreakdown': {
                        'compliance_disclosure': {'label': 'Disclosure', 'passed': 9, 'failed': 1, 'total': 10},
                    },
                    'flagStats': {
                        'escalation': {'relevant': 4, 'notRelevant': 6, 'present': 1},
                        'disagreement': {'relevant': 5, 'notRelevant': 5, 'present': 2},
                        'tension': {'relevant': 3, 'notRelevant': 7, 'bySeverity': {'high': 1}},
                        'meetingSetup': {'relevant': 10, 'notRelevant': 0, 'attempted': 4, 'accepted': 0},
                    },
                    'narrative': {
                        'dimensionInsights': [
                            {'dimension': 'Discovery', 'insight': 'Discovery quality is inconsistent.', 'priority': 'P1'},
                        ],
                        'complianceAlerts': ['Disclosure missed in some calls'],
                        'recommendations': [{'priority': 'P0', 'action': 'Coach disclosure opener'}],
                        'flagPatterns': 'Escalations correlate with weak discovery.',
                    },
                },
            ),
            (
                {
                    'id': 'sales-2',
                    'created_at': '2026-03-02T00:00:00+00:00',
                    'batch_metadata': {'run_name': 'Sales Run 2'},
                },
                {
                    'metadata': {'runName': 'Sales Run 2'},
                    'runSummary': {
                        'totalCalls': 8,
                        'evaluatedCalls': 8,
                        'avgQaScore': 73,
                        'compliancePassRate': 75,
                    },
                    'dimensionBreakdown': {
                        'discovery': {
                            'label': 'Discovery',
                            'avg': 72,
                            'maxPossible': 100,
                            'greenThreshold': 80,
                            'yellowThreshold': 60,
                        },
                    },
                    'complianceBreakdown': {
                        'compliance_disclosure': {'label': 'Disclosure', 'passed': 6, 'failed': 2, 'total': 8},
                    },
                    'flagStats': {
                        'escalation': {'relevant': 2, 'notRelevant': 6, 'present': 1},
                        'disagreement': {'relevant': 2, 'notRelevant': 6, 'present': 1},
                        'tension': {'relevant': 2, 'notRelevant': 6, 'bySeverity': {'medium': 2}},
                        'meetingSetup': {'relevant': 8, 'notRelevant': 0, 'attempted': 2, 'accepted': 0},
                    },
                    'narrative': {
                        'dimensionInsights': [
                            {'dimension': 'Discovery', 'insight': 'Discovery remains shallow.', 'priority': 'P1'},
                        ],
                        'complianceAlerts': ['Disclosure still missed'],
                        'recommendations': [{'priority': 'P1', 'action': 'Reinforce objection handling'}],
                        'flagPatterns': 'Tension increases when next steps are unclear.',
                    },
                },
            ),
        ]

        analytics = InsideSalesCrossRunAggregator(runs_data, 4).aggregate()

        self.assertEqual(analytics.stats.total_runs, 2)
        self.assertEqual(analytics.stats.all_runs, 4)
        self.assertEqual(analytics.stats.total_calls, 20)
        self.assertEqual(analytics.dimension_heatmap.rows[0].key, 'discovery')
        self.assertEqual(analytics.compliance_heatmap.rows[0].key, 'compliance_disclosure')
        self.assertEqual(analytics.flag_rollups.behavioral['escalation'].present, 2)
        self.assertGreaterEqual(len(analytics.issues_and_recommendations.issues), 1)
        self.assertGreaterEqual(len(analytics.issues_and_recommendations.recommendations), 1)


class KairaCrossRunCanonicalAdapterTests(unittest.TestCase):
    """The live cross-run path emits a trend_chart + insight_panels payload."""

    def _kaira_analytics_config(self):
        from app.schemas.app_config import AppConfig
        from app.services.seed_defaults import APP_SEEDS

        for seed in APP_SEEDS:
            if seed['slug'] == 'kaira-bot':
                return AppConfig.model_validate(seed['config']).analytics
        raise KeyError('kaira-bot')

    def _run_payload(self, run_name: str, health: float) -> dict:
        # Minimal canonical per-run payload carrying only the sections the
        # cross-run adapter reads for trend + insights. Distributions are
        # omitted deliberately — they exercise an unrelated goal-rate path.
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
                    'id': 'kaira-metrics',
                    'type': 'metric_breakdown',
                    'title': 'Metrics',
                    'data': [
                        {'key': 'intent-accuracy', 'label': 'Intent Accuracy', 'value': health - 2, 'maxValue': 100},
                        {'key': 'correctness-rate', 'label': 'Correctness Rate', 'value': health + 2, 'maxValue': 100},
                    ],
                },
                {
                    'id': 'kaira-recommendations',
                    'type': 'issues_recommendations',
                    'title': 'Issues',
                    'data': {
                        'issues': [
                            {'title': 'Intent slips', 'area': 'Intent', 'priority': 'P0', 'summary': 'Intent routing degraded on pricing.'},
                        ],
                        'recommendations': [
                            {'priority': 'P0', 'title': 'Intent', 'action': 'Tighten routing examples', 'expectedImpact': '-3 intent failures'},
                        ],
                    },
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
                'blocks': [
                    {'id': 'cover', 'type': 'cover', 'title': run_name},
                ],
            },
        }

    def _runs_data(self):
        return [
            ({'id': 'run-1', 'created_at': '2026-03-01T00:00:00+00:00'}, self._run_payload('Run 1', 82.0)),
            ({'id': 'run-2', 'created_at': '2026-03-02T00:00:00+00:00'}, self._run_payload('Run 2', 76.0)),
        ]

    def test_from_runs_emits_trend_chart_and_insight_panels(self):
        from app.services.reports.canonical_adapters import (
            adapt_kaira_cross_run_from_runs,
        )
        from app.services.reports.contracts.report_sections import (
            InsightPanelsSection,
            TrendChartSection,
        )

        runs = self._runs_data()
        report = adapt_kaira_cross_run_from_runs(
            runs, self._kaira_analytics_config(), app_id='kaira-bot', total_runs_available=2
        )
        by_id = {section.id: section for section in report.sections}

        trend = by_id['kaira-cross-trend']
        self.assertIsInstance(trend, TrendChartSection)
        self.assertEqual(len(trend.data.points), len(runs))
        for point in trend.data.points:
            self.assertTrue(point.bucket)
            self.assertIsInstance(point.primary, float)
            self.assertIsInstance(point.breakdown, dict)
        self.assertEqual(trend.data.primary_label, 'Health Score')
        self.assertEqual(trend.data.y_domain, (0.0, 100.0))
        self.assertIsNotNone(trend.data.reference_value)
        self.assertEqual(trend.data.reference_label, 'Average')
        self.assertTrue(trend.data.breakdowns)

        insights = by_id['kaira-cross-insights']
        self.assertIsInstance(insights, InsightPanelsSection)
        self.assertGreaterEqual(len(insights.data), 1)
        for panel in insights.data:
            self.assertTrue(panel.area)
            self.assertTrue(panel.priority)
            self.assertGreaterEqual(panel.run_count, 1)
            self.assertTrue(panel.items)

        self.assertNotIn('kaira-cross-issues', by_id)

    def test_payload_dicts_validate_as_section_models(self):
        from app.services.reports.canonical_adapters import (
            adapt_kaira_cross_run_from_runs,
        )
        from app.services.reports.contracts.report_sections import (
            InsightPanelsSection,
            TrendChartSection,
        )

        runs = self._runs_data()
        report = adapt_kaira_cross_run_from_runs(
            runs, self._kaira_analytics_config(), app_id='kaira-bot', total_runs_available=2
        )
        types = {section.type for section in report.sections}
        self.assertIn('trend_chart', types)
        self.assertIn('insight_panels', types)
        self.assertNotIn('issues_recommendations', types)
        self.assertNotIn(
            'metric_breakdown',
            {s.type for s in report.sections if s.id == 'kaira-cross-trend'},
        )

        trend = next(s for s in report.sections if s.id == 'kaira-cross-trend')
        rebuilt_trend = TrendChartSection.model_validate(trend.model_dump(by_alias=True))
        self.assertEqual(len(rebuilt_trend.data.points), len(runs))

        insights = next(s for s in report.sections if s.id == 'kaira-cross-insights')
        rebuilt_insights = InsightPanelsSection.model_validate(insights.model_dump(by_alias=True))
        self.assertGreaterEqual(len(rebuilt_insights.data), 1)


class VoiceRxCrossRunAggregatorTests(unittest.TestCase):
    """build_voice_rx_cross_run_payload emits trend_chart + insight_panels."""

    def _voice_rx_analytics_config(self):
        from app.schemas.app_config import AppConfig
        from app.services.seed_defaults import APP_SEEDS

        for seed in APP_SEEDS:
            if seed['slug'] == 'voice-rx':
                return AppConfig.model_validate(seed['config']).analytics
        raise KeyError('voice-rx')

    def _run_payload(self, run_name: str, accuracy: float) -> dict:
        # Minimal canonical per-run payload carrying sections the cross-run
        # aggregator reads: voice-rx-summary (accuracy cards) and voice-rx-severity.
        return {
            'schemaVersion': 'v1',
            'metadata': {
                'appId': 'voice-rx',
                'runId': run_name,
                'runName': run_name,
                'evalType': 'batch',
                'createdAt': '2026-04-01T00:00:00+00:00',
                'computedAt': '2026-04-01T00:05:00+00:00',
            },
            'sections': [
                {
                    'id': 'voice-rx-summary',
                    'type': 'summary_cards',
                    'title': 'Accuracy Summary',
                    'data': [
                        {'key': 'overall-accuracy', 'label': 'Overall Accuracy', 'value': f'{accuracy:.1f}%', 'tone': 'positive'},
                        {'key': 'total-items', 'label': 'Total Items', 'value': '20', 'tone': 'neutral'},
                        {'key': 'critical-errors', 'label': 'Critical Errors', 'value': '1', 'tone': 'negative'},
                    ],
                },
                {
                    'id': 'voice-rx-severity',
                    'type': 'distribution_chart',
                    'title': 'Severity Distribution',
                    'data': [
                        {
                            'label': 'Severity',
                            'values': [3.0, 5.0, 12.0],
                            'categories': ['CRITICAL', 'HIGH', 'LOW'],
                        }
                    ],
                },
                {
                    'id': 'voice-rx-issues',
                    'type': 'issues_recommendations',
                    'title': 'Issues',
                    'data': {
                        'issues': [
                            {'title': 'Dosage transcription error', 'area': 'Accuracy', 'priority': 'P0', 'summary': 'Wrong dose captured.'},
                        ],
                        'recommendations': [],
                    },
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

    def _runs_data(self):
        return [
            ({'id': 'run-1', 'created_at': '2026-04-01T00:00:00+00:00'}, self._run_payload('Run 1', 88.5)),
            ({'id': 'run-2', 'created_at': '2026-04-02T00:00:00+00:00'}, self._run_payload('Run 2', 92.0)),
        ]

    def test_emits_trend_chart_and_insight_panels(self):
        from app.services.reports.voice_rx_cross_run import build_voice_rx_cross_run_payload
        from app.services.reports.contracts.report_sections import (
            InsightPanelsSection,
            TrendChartSection,
        )

        runs = self._runs_data()
        report = build_voice_rx_cross_run_payload(
            runs, self._voice_rx_analytics_config(), app_id='voice-rx', total_runs_available=2
        )
        by_id = {section.id: section for section in report.sections}

        trend = by_id['voice-rx-cross-metrics']
        self.assertIsInstance(trend, TrendChartSection)
        self.assertEqual(len(trend.data.points), len(runs))
        for point in trend.data.points:
            self.assertTrue(point.bucket)
            self.assertIsInstance(point.primary, float)
            self.assertIsInstance(point.breakdown, dict)
        self.assertEqual(trend.data.primary_label, 'Overall Accuracy')
        self.assertEqual(trend.data.y_domain, (0.0, 100.0))
        self.assertIsNotNone(trend.data.reference_value)
        self.assertEqual(trend.data.reference_label, 'Average')

        insights = by_id['voice-rx-cross-insights']
        self.assertIsInstance(insights, InsightPanelsSection)
        self.assertGreaterEqual(len(insights.data), 1)
        for panel in insights.data:
            self.assertTrue(panel.area)
            self.assertTrue(panel.priority)
            self.assertGreaterEqual(panel.run_count, 1)
            self.assertTrue(panel.items)

        self.assertNotIn('voice-rx-cross-issues', by_id)

    def test_payload_dicts_validate_as_section_models(self):
        from app.services.reports.voice_rx_cross_run import build_voice_rx_cross_run_payload
        from app.services.reports.contracts.report_sections import (
            InsightPanelsSection,
            TrendChartSection,
        )

        runs = self._runs_data()
        report = build_voice_rx_cross_run_payload(
            runs, self._voice_rx_analytics_config(), app_id='voice-rx', total_runs_available=2
        )
        types = {section.type for section in report.sections}
        self.assertIn('trend_chart', types)
        self.assertIn('insight_panels', types)
        self.assertNotIn('issues_recommendations', types)
        self.assertNotIn(
            'metric_breakdown',
            {s.type for s in report.sections if s.id == 'voice-rx-cross-metrics'},
        )

        trend = next(s for s in report.sections if s.id == 'voice-rx-cross-metrics')
        rebuilt_trend = TrendChartSection.model_validate(trend.model_dump(by_alias=True))
        self.assertEqual(len(rebuilt_trend.data.points), len(runs))

        insights = next(s for s in report.sections if s.id == 'voice-rx-cross-insights')
        rebuilt_insights = InsightPanelsSection.model_validate(insights.model_dump(by_alias=True))
        self.assertGreaterEqual(len(rebuilt_insights.data), 1)

    def test_no_severity_data_produces_empty_breakdown(self):
        """Runs with no severity section emit zero-breakdown trend points without error."""
        from app.services.reports.voice_rx_cross_run import build_voice_rx_cross_run_payload

        payload = self._run_payload('Run X', 85.0)
        payload['sections'] = [s for s in payload['sections'] if s['id'] != 'voice-rx-severity']
        runs = [({'id': 'run-x', 'created_at': '2026-04-01T00:00:00+00:00'}, payload)]
        report = build_voice_rx_cross_run_payload(
            runs, self._voice_rx_analytics_config(), app_id='voice-rx', total_runs_available=1
        )
        by_id = {section.id: section for section in report.sections}
        trend = by_id['voice-rx-cross-metrics']
        self.assertEqual(len(trend.data.points), 1)
        self.assertEqual(trend.data.points[0].breakdown, {})


class InsideSalesCrossRunCanonicalAdapterTests(unittest.TestCase):
    """adapt_inside_sales_cross_run_from_runs emits trend_chart + insight_panels."""

    def _inside_sales_analytics_config(self):
        from app.schemas.app_config import AppConfig
        from app.services.seed_defaults import APP_SEEDS

        for seed in APP_SEEDS:
            if seed['slug'] == 'inside-sales':
                return AppConfig.model_validate(seed['config']).analytics
        raise KeyError('inside-sales')

    def _run_payload(self, run_name: str, qa_score: float) -> dict:
        # Minimal canonical per-run payload for the inside-sales cross-run adapter.
        # Carries inside-sales-summary (qa/compliance cards) and
        # inside-sales-recommendations (issues + recs).
        return {
            'schemaVersion': 'v1',
            'metadata': {
                'appId': 'inside-sales',
                'runId': run_name,
                'runName': run_name,
                'evalType': 'batch',
                'createdAt': '2026-04-01T00:00:00+00:00',
                'computedAt': '2026-04-01T00:05:00+00:00',
            },
            'sections': [
                {
                    'id': 'inside-sales-summary',
                    'type': 'summary_cards',
                    'title': 'Run Summary',
                    'data': [
                        {'key': 'avg-qa-score', 'label': 'Avg QA Score', 'value': f'{qa_score:.1f}', 'tone': 'positive'},
                        {'key': 'evaluated-calls', 'label': 'Evaluated Calls', 'value': '10', 'tone': 'neutral'},
                        {'key': 'total-calls', 'label': 'Total Calls', 'value': '12', 'tone': 'neutral'},
                        {'key': 'compliance-pass-rate', 'label': 'Compliance Pass Rate', 'value': '85.0%', 'tone': 'positive'},
                    ],
                },
                {
                    'id': 'inside-sales-dimensions',
                    'type': 'metric_breakdown',
                    'title': 'Dimensions',
                    'data': [
                        {'key': 'discovery', 'label': 'Discovery', 'value': qa_score - 5, 'maxValue': 100},
                        {'key': 'objection_handling', 'label': 'Objection Handling', 'value': qa_score + 2, 'maxValue': 100},
                    ],
                },
                {
                    'id': 'inside-sales-recommendations',
                    'type': 'issues_recommendations',
                    'title': 'Issues & Recs',
                    'data': {
                        'issues': [
                            {'title': 'Discovery weakness', 'area': 'Discovery', 'priority': 'P1', 'summary': 'Discovery scores are below target.'},
                        ],
                        'recommendations': [
                            {'priority': 'P1', 'title': 'Coaching Recommendation', 'action': 'Coach agents on discovery questions.'},
                        ],
                    },
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

    def _runs_data(self):
        return [
            ({'id': 'run-1', 'created_at': '2026-04-01T00:00:00+00:00'}, self._run_payload('Run 1', 78.0)),
            ({'id': 'run-2', 'created_at': '2026-04-02T00:00:00+00:00'}, self._run_payload('Run 2', 84.0)),
        ]

    def test_from_runs_emits_trend_chart_and_insight_panels(self):
        from app.services.reports.canonical_adapters import (
            adapt_inside_sales_cross_run_from_runs,
        )
        from app.services.reports.contracts.report_sections import (
            InsightPanelsSection,
            TrendChartSection,
        )

        runs = self._runs_data()
        report = adapt_inside_sales_cross_run_from_runs(
            runs, self._inside_sales_analytics_config(), app_id='inside-sales', total_runs_available=2
        )
        by_id = {section.id: section for section in report.sections}

        trend = by_id['inside-sales-cross-trend']
        self.assertIsInstance(trend, TrendChartSection)
        self.assertEqual(len(trend.data.points), len(runs))
        for point in trend.data.points:
            self.assertTrue(point.bucket)
            self.assertIsInstance(point.primary, float)
            self.assertIsInstance(point.breakdown, dict)
        self.assertEqual(trend.data.primary_label, 'QA Score')
        self.assertEqual(trend.data.y_domain, (0.0, 100.0))
        self.assertIsNotNone(trend.data.reference_value)
        self.assertEqual(trend.data.reference_label, 'Average')
        self.assertTrue(trend.data.breakdowns)

        insights = by_id['inside-sales-cross-insights']
        self.assertIsInstance(insights, InsightPanelsSection)
        self.assertGreaterEqual(len(insights.data), 1)
        for panel in insights.data:
            self.assertTrue(panel.area)
            self.assertTrue(panel.priority)
            self.assertGreaterEqual(panel.run_count, 1)
            self.assertTrue(panel.items)

        self.assertNotIn('inside-sales-cross-issues', by_id)

    def test_payload_dicts_validate_as_section_models(self):
        from app.services.reports.canonical_adapters import (
            adapt_inside_sales_cross_run_from_runs,
        )
        from app.services.reports.contracts.report_sections import (
            InsightPanelsSection,
            TrendChartSection,
        )

        runs = self._runs_data()
        report = adapt_inside_sales_cross_run_from_runs(
            runs, self._inside_sales_analytics_config(), app_id='inside-sales', total_runs_available=2
        )
        types = {section.type for section in report.sections}
        self.assertIn('trend_chart', types)
        self.assertIn('insight_panels', types)
        self.assertNotIn('issues_recommendations', types)

        trend = next(s for s in report.sections if s.id == 'inside-sales-cross-trend')
        rebuilt_trend = TrendChartSection.model_validate(trend.model_dump(by_alias=True))
        self.assertEqual(len(rebuilt_trend.data.points), len(runs))

        insights = next(s for s in report.sections if s.id == 'inside-sales-cross-insights')
        rebuilt_insights = InsightPanelsSection.model_validate(insights.model_dump(by_alias=True))
        self.assertGreaterEqual(len(rebuilt_insights.data), 1)

    def test_missing_dimensions_produce_empty_breakdown(self):
        """Runs with no dimensions section emit zero-breakdown trend points without error."""
        from app.services.reports.canonical_adapters import (
            adapt_inside_sales_cross_run_from_runs,
        )

        payload = self._run_payload('Run X', 80.0)
        payload['sections'] = [s for s in payload['sections'] if s['id'] != 'inside-sales-dimensions']
        runs = [({'id': 'run-x', 'created_at': '2026-04-01T00:00:00+00:00'}, payload)]
        report = adapt_inside_sales_cross_run_from_runs(
            runs, self._inside_sales_analytics_config(), app_id='inside-sales', total_runs_available=1
        )
        by_id = {section.id: section for section in report.sections}
        trend = by_id['inside-sales-cross-trend']
        self.assertEqual(len(trend.data.points), 1)
        self.assertEqual(trend.data.points[0].breakdown, {})


if __name__ == '__main__':
    unittest.main()
