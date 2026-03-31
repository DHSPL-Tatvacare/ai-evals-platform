"""unittest coverage for pure cross-run aggregators."""

import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


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


if __name__ == '__main__':
    unittest.main()
