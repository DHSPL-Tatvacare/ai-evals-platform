"""Focused backend coverage for thread rule-compliance canonicalization."""

import os
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.evaluators.correctness_evaluator import CorrectnessEvaluator  # noqa: E402
from app.services.evaluators.efficiency_evaluator import EfficiencyEvaluator  # noqa: E402
from app.services.evaluators.models import RuleCompliance  # noqa: E402
from app.services.evaluators.rule_catalog import PromptRule  # noqa: E402
from app.services.evaluators.thread_canonical import (  # noqa: E402
    build_canonical_thread_evaluation,
    enrich_thread_result_for_api,
)  # noqa: E402
from app.services.reports.aggregator import ReportAggregator  # noqa: E402


def _rule(rule_id: str, section: str = 'Prompt Section') -> PromptRule:
    return PromptRule(
        rule_id=rule_id,
        section=section,
        rule_text=f'Rule text for {rule_id}',
        goal_ids=['meal_logged'],
        evaluation_scopes=['correctness', 'efficiency'],
    )


class RuleComplianceContractTests(unittest.TestCase):
    def test_followed_true_without_status_normalizes_to_followed(self):
        outcome = RuleCompliance(
            rule_id='ask_time_if_missing',
            section='Time Validation Instructions',
            followed=True,
            evidence='The bot asked for the meal time.',
        )

        self.assertEqual(outcome.status, 'FOLLOWED')
        self.assertTrue(outcome.followed)

    def test_followed_false_without_status_normalizes_to_violated(self):
        outcome = RuleCompliance(
            rule_id='apply_user_corrections',
            section='Edit Operation Prompt Construction',
            followed=False,
            evidence='The correction was ignored.',
        )

        self.assertEqual(outcome.status, 'VIOLATED')
        self.assertFalse(outcome.followed)

    def test_not_applicable_keeps_followed_none(self):
        outcome = RuleCompliance(
            rule_id='question_only_rule',
            section='Question Answering',
            followed=True,
            evidence='No question was asked.',
            status='NOT_APPLICABLE',
        )

        self.assertEqual(outcome.status, 'NOT_APPLICABLE')
        self.assertIsNone(outcome.followed)


class EvaluatorParserCompatibilityTests(unittest.TestCase):
    def test_efficiency_parser_accepts_status_payloads_and_marks_omitted_rules_not_evaluated(self):
        rules = [_rule('ask_time_if_missing', 'Time Validation'), _rule('apply_user_corrections', 'Edits')]

        parsed = EfficiencyEvaluator._parse_rule_compliance(
            [
                {
                    'rule_id': 'ask_time_if_missing',
                    'status': 'NOT_APPLICABLE',
                    'evidence': 'The thread was not a meal-logging flow.',
                }
            ],
            rules,
        )

        by_rule = {item.rule_id: item for item in parsed}
        self.assertEqual(by_rule['ask_time_if_missing'].status, 'NOT_APPLICABLE')
        self.assertIsNone(by_rule['ask_time_if_missing'].followed)
        self.assertEqual(by_rule['apply_user_corrections'].status, 'NOT_EVALUATED')
        self.assertIsNone(by_rule['apply_user_corrections'].followed)

    def test_correctness_parser_accepts_legacy_followed_payloads(self):
        rules = [_rule('exact_calorie_values', 'Nutrition Data Context')]

        parsed = CorrectnessEvaluator._parse_rule_compliance(
            [
                {
                    'rule_id': 'exact_calorie_values',
                    'followed': False,
                    'evidence': 'The calories were rounded to 200.',
                }
            ],
            rules,
        )

        self.assertEqual(parsed[0].status, 'VIOLATED')
        self.assertFalse(parsed[0].followed)


class CanonicalThreadAdapterTests(unittest.TestCase):
    def test_builder_derives_canonical_rule_truth_and_summary(self):
        canonical = build_canonical_thread_evaluation(
            {
                'thread': {
                    'thread_id': 'thrd-1',
                    'user_id': 'user-1',
                    'message_count': 2,
                    'duration_seconds': 31,
                    'messages': [
                        {
                            'query_text': 'Log this meal',
                            'final_response_message': 'Please confirm',
                            'intent_detected': 'meal_logging',
                            'has_image': True,
                            'timestamp': '2026-04-01T10:00:00+00:00',
                        }
                    ],
                },
                'intent_accuracy': 1.0,
                'correctness_evaluations': [
                    {
                        'message': {
                            'query_text': 'Log this meal',
                            'final_response_message': 'Please confirm',
                            'intent_detected': 'meal_logging',
                            'has_image': True,
                            'timestamp': '2026-04-01T10:00:00+00:00',
                        },
                        'verdict': 'HARD FAIL',
                        'reasoning': 'Calories are implausible.',
                        'has_image_context': True,
                        'rule_compliance': [
                            {
                                'rule_id': 'exact_calorie_values',
                                'section': 'Nutrition Data Context',
                                'status': 'VIOLATED',
                                'followed': False,
                                'evidence': 'The calorie value is off by an order of magnitude.',
                            },
                            {
                                'rule_id': 'single_item_one_table',
                                'section': 'Formatting',
                                'status': 'NOT_APPLICABLE',
                                'followed': None,
                                'evidence': 'The response contained multiple food items.',
                            },
                        ],
                    }
                ],
                'efficiency_evaluation': {
                    'verdict': 'NOT APPLICABLE',
                    'task_completed': True,
                    'reasoning': 'This was a query-response interaction.',
                    'recovery_quality': 'NOT NEEDED',
                    'friction_turns': [],
                    'failure_reason': '',
                    'rule_compliance': [
                        {
                            'rule_id': 'ask_time_if_missing',
                            'section': 'Time Validation',
                            'status': 'NOT_EVALUATED',
                            'followed': None,
                            'evidence': 'Not evaluated by judge',
                        },
                        {
                            'rule_id': 'apply_user_corrections',
                            'section': 'Edits',
                            'followed': True,
                            'evidence': 'The bot handled the correction correctly.',
                        },
                    ],
                },
                'success_status': False,
                'failed_evaluators': {'intent': 'timeout'},
                'skipped_evaluators': ['custom'],
            }
        )

        self.assertEqual(canonical['evaluators']['correctness']['worstVerdict'], 'HARD_FAIL')
        self.assertEqual(canonical['evaluators']['efficiency']['verdict'], 'NOT_APPLICABLE')
        self.assertTrue(canonical['facts']['thread']['hasImage'])
        self.assertTrue(canonical['facts']['execution']['hadEvaluationError'])
        self.assertEqual(canonical['derived']['ruleComplianceSummary']['followed'], 1)
        self.assertEqual(canonical['derived']['ruleComplianceSummary']['violated'], 1)
        self.assertEqual(canonical['derived']['ruleComplianceSummary']['notApplicable'], 1)
        self.assertEqual(canonical['derived']['ruleComplianceSummary']['notEvaluated'], 1)
        self.assertEqual(canonical['derived']['ruleComplianceSummary']['evaluatedCount'], 2)

        by_rule = {item['ruleId']: item for item in canonical['derived']['canonicalRuleOutcomes']}
        self.assertEqual(by_rule['apply_user_corrections']['status'], 'FOLLOWED')
        self.assertEqual(by_rule['exact_calorie_values']['status'], 'VIOLATED')
        self.assertEqual(by_rule['single_item_one_table']['status'], 'NOT_APPLICABLE')
        self.assertEqual(by_rule['ask_time_if_missing']['status'], 'NOT_EVALUATED')

    def test_api_enrichment_exposes_canonical_thread_without_dropping_legacy_fields(self):
        enriched = enrich_thread_result_for_api(
            {
                'thread': {
                    'thread_id': 'thrd-2',
                    'user_id': 'user-2',
                    'message_count': 1,
                    'duration_seconds': 10,
                    'messages': [],
                },
                'correctness_evaluations': [],
                'efficiency_evaluation': {
                    'verdict': 'EFFICIENT',
                    'task_completed': True,
                    'friction_turns': [],
                    'recovery_quality': 'NOT NEEDED',
                    'failure_reason': '',
                    'reasoning': 'Quick successful flow.',
                    'rule_compliance': [],
                },
                'success_status': True,
            },
            row_success_status=True,
            row_efficiency_verdict='EFFICIENT',
            row_worst_correctness=None,
            row_intent_accuracy=None,
        )

        self.assertIn('canonical_thread', enriched)
        self.assertIn('efficiency_evaluation', enriched)
        self.assertTrue(enriched['canonical_thread']['derived']['successStatus'])

class ThreadReportAggregatorTests(unittest.TestCase):
    def test_rule_matrix_counts_only_followed_and_violated(self):
        threads = [
            SimpleNamespace(
                thread_id='thrd-1',
                intent_accuracy=1.0,
                worst_correctness='PASS',
                efficiency_verdict='ACCEPTABLE',
                success_status=True,
                result={
                    'canonical_thread': {
                        'facts': {'thread': {}, 'execution': {}},
                        'evaluators': {},
                        'derived': {
                            'canonicalRuleOutcomes': [
                                {'ruleId': 'rule-a', 'section': 'Prompt', 'status': 'FOLLOWED', 'evidence': 'ok'},
                                {'ruleId': 'rule-b', 'section': 'Prompt', 'status': 'NOT_APPLICABLE', 'evidence': 'n/a'},
                            ],
                        },
                    }
                },
            ),
            SimpleNamespace(
                thread_id='thrd-2',
                intent_accuracy=0.5,
                worst_correctness='HARD FAIL',
                efficiency_verdict='BROKEN',
                success_status=False,
                result={
                    'canonical_thread': {
                        'facts': {'thread': {}, 'execution': {}},
                        'evaluators': {},
                        'derived': {
                            'canonicalRuleOutcomes': [
                                {'ruleId': 'rule-a', 'section': 'Prompt', 'status': 'VIOLATED', 'evidence': 'bad'},
                                {'ruleId': 'rule-b', 'section': 'Prompt', 'status': 'NOT_EVALUATED', 'evidence': 'unknown'},
                            ],
                        },
                    }
                },
            ),
        ]

        matrix = ReportAggregator(threads, [], {}).compute_rule_compliance()
        by_rule = {item.rule_id: item for item in matrix.rules}

        self.assertEqual(by_rule['rule-a'].passed, 1)
        self.assertEqual(by_rule['rule-a'].failed, 1)
        self.assertNotIn('rule-b', by_rule)

    def test_exemplar_violation_extraction_ignores_unknown_and_not_applicable(self):
        violations = ReportAggregator._extract_violations(
            {
                'canonical_thread': {
                    'facts': {'thread': {}, 'execution': {}},
                    'evaluators': {},
                    'derived': {
                        'canonicalRuleOutcomes': [
                            {'ruleId': 'rule-a', 'section': 'Prompt', 'status': 'VIOLATED', 'evidence': 'bad'},
                            {'ruleId': 'rule-b', 'section': 'Prompt', 'status': 'NOT_APPLICABLE', 'evidence': 'n/a'},
                            {'ruleId': 'rule-c', 'section': 'Prompt', 'status': 'NOT_EVALUATED', 'evidence': 'unknown'},
                        ],
                    },
                }
            }
        )

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].rule_id, 'rule-a')


if __name__ == '__main__':
    unittest.main()
