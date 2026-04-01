"""Focused backend coverage for adversarial pipeline canonicalization phases 1-3."""

import os
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.evaluators.adversarial_config import (  # noqa: E402
    AdversarialConfig,
    AdversarialGoal,
    AdversarialRule,
    get_default_config,
)
from app.services.evaluators.adversarial_evaluator import AdversarialEvaluator  # noqa: E402
from app.services.evaluators.adversarial_canonical import (  # noqa: E402
    build_canonical_adversarial_case,
    enrich_adversarial_result_for_api,
)
from app.services.evaluators.conversation_agent import ConversationAgent  # noqa: E402
from app.services.evaluators.kaira_client import KairaAPIError, KairaStreamResponse  # noqa: E402
from app.services.evaluators.llm_base import BaseLLMProvider  # noqa: E402
from app.services.evaluators.models import (  # noqa: E402
    AdversarialTestCase,
    ConversationTranscript,
    ConversationTurn,
    GoalTransition,
    SimulatorState,
    TransportFacts,
)
from app.services.reports.aggregator import AdversarialAggregator  # noqa: E402


class FakeLLMProvider(BaseLLMProvider):
    def __init__(self, *, text_responses=None, json_responses=None):
        super().__init__(api_key='', model_name='fake-model', temperature=0.0)
        self.text_responses = list(text_responses or [])
        self.json_responses = list(json_responses or [])
        self.generate_calls = []
        self.generate_json_calls = []

    async def generate(self, prompt, system_prompt=None, response_format=None, **kwargs):
        self.generate_calls.append(
            {
                'prompt': prompt,
                'system_prompt': system_prompt,
                'response_format': response_format,
                'kwargs': kwargs,
            }
        )
        if not self.text_responses:
            raise AssertionError('No fake text response left for generate()')
        return self.text_responses.pop(0)

    async def generate_json(self, prompt, system_prompt=None, json_schema=None, **kwargs):
        self.generate_json_calls.append(
            {
                'prompt': prompt,
                'system_prompt': system_prompt,
                'json_schema': json_schema,
                'kwargs': kwargs,
            }
        )
        if not self.json_responses:
            raise AssertionError('No fake JSON response left for generate_json()')
        return self.json_responses.pop(0)


class FakeKairaClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.queries = []

    async def stream_message(self, query, user_id, session_state, test_case_label=None):
        self.queries.append(query)
        if not self.responses:
            raise AssertionError('No fake Kaira response left')

        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response

        session_state.thread_id = session_state.thread_id or 'thread-1'
        session_state.session_id = session_state.session_id or 'session-1'
        session_state.response_id = f'response-{len(self.queries)}'
        session_state.is_first_message = False
        return response


def _goal(goal_id: str, label: str) -> AdversarialGoal:
    return AdversarialGoal(
        id=goal_id,
        label=label,
        description=f'{label} goal',
        completion_criteria=[f'{label} completed'],
        not_completion=[f'{label} still in progress'],
        agent_behavior=f'Pursue {label}',
        signal_patterns=[],
        enabled=True,
    )


def _test_case(goal_flow):
    return AdversarialTestCase(
        synthetic_input='Log my lunch',
        expected_behavior='',
        difficulty='MEDIUM',
        goal_flow=goal_flow,
        active_traits=[],
        expected_challenges=[],
    )


class ConversationAgentPhaseOneTests(unittest.IsolatedAsyncioTestCase):
    async def test_goal_complete_transition_generates_fresh_next_goal_opener(self):
        llm = FakeLLMProvider(
            text_responses=[
                'GOAL_COMPLETE:meal_logged',
                'What foods have a lot of fiber?',
                'GOAL_COMPLETE:question_answered',
            ]
        )
        agent = ConversationAgent(llm_provider=llm, max_turns=3)
        client = FakeKairaClient(
            responses=[
                KairaStreamResponse(full_message='Your meal has been logged.'),
                KairaStreamResponse(full_message='Beans, lentils, oats, and berries are good fiber sources.'),
            ]
        )

        transcript = await agent.run_conversation(
            test_case=_test_case(['meal_logged', 'question_answered']),
            goals=[_goal('meal_logged', 'Meal Logging'), _goal('question_answered', 'Question Answered')],
            client=client,
            user_id='user-1',
            turn_delay=0,
        )

        self.assertEqual(
            client.queries,
            ['Log my lunch', 'What foods have a lot of fiber?'],
        )
        self.assertEqual(transcript.goals_completed, ['meal_logged', 'question_answered'])
        self.assertEqual(
            [(t.goal_id, t.event, t.at_turn) for t in transcript.goal_transitions],
            [
                ('meal_logged', 'started', 1),
                ('meal_logged', 'completed', 1),
                ('question_answered', 'started', 2),
                ('question_answered', 'completed', 2),
            ],
        )

    async def test_goal_abandonment_transition_generates_fresh_next_goal_opener(self):
        llm = FakeLLMProvider(
            text_responses=[
                'GOAL_ABANDONED:meal_logged',
                'Can you explain carbs in simple terms?',
                'GOAL_COMPLETE',
            ]
        )
        agent = ConversationAgent(llm_provider=llm, max_turns=3)
        client = FakeKairaClient(
            responses=[
                KairaStreamResponse(full_message='I still need more meal details.'),
                KairaStreamResponse(full_message="Carbs are your body's main quick energy source."),
            ]
        )

        transcript = await agent.run_conversation(
            test_case=_test_case(['meal_logged', 'question_answered']),
            goals=[_goal('meal_logged', 'Meal Logging'), _goal('question_answered', 'Question Answered')],
            client=client,
            user_id='user-1',
            turn_delay=0,
        )

        self.assertEqual(
            client.queries,
            ['Log my lunch', 'Can you explain carbs in simple terms?'],
        )
        self.assertEqual(transcript.goals_abandoned, ['meal_logged'])
        self.assertEqual(transcript.goals_completed, ['question_answered'])

    async def test_transport_facts_capture_stream_errors_and_partial_responses(self):
        llm = FakeLLMProvider(text_responses=['GOAL_COMPLETE'])
        agent = ConversationAgent(llm_provider=llm, max_turns=1)
        client = FakeKairaClient(
            responses=[
                KairaStreamResponse(
                    full_message='Fallback agent answer',
                    agent_responses=[{'agent': 'FoodAgent', 'message': 'Fallback agent answer', 'success': True}],
                    stream_errors=['summary chunk failed'],
                    saw_agent_message=True,
                    saw_summary_chunk=False,
                    had_partial_response=True,
                )
            ]
        )

        transcript = await agent.run_conversation(
            test_case=_test_case(['meal_logged']),
            goals=[_goal('meal_logged', 'Meal Logging')],
            client=client,
            user_id='user-1',
            turn_delay=0,
        )

        self.assertTrue(transcript.transport.had_stream_error)
        self.assertTrue(transcript.transport.had_partial_response)
        self.assertEqual(transcript.transport.stream_errors, ['summary chunk failed'])

    async def test_transport_facts_capture_timeout_errors(self):
        llm = FakeLLMProvider(text_responses=[])
        agent = ConversationAgent(llm_provider=llm, max_turns=1)
        client = FakeKairaClient(
            responses=[
                KairaAPIError(
                    status=0,
                    message='Request timed out — Kaira API did not respond in time',
                    url='https://kaira.test/chat/stream',
                    kind='timeout',
                )
            ]
        )

        transcript = await agent.run_conversation(
            test_case=_test_case(['meal_logged']),
            goals=[_goal('meal_logged', 'Meal Logging')],
            client=client,
            user_id='user-1',
            turn_delay=0,
        )

        self.assertEqual(transcript.stop_reason, 'error')
        self.assertTrue(transcript.transport.had_timeout)
        self.assertFalse(transcript.transport.had_http_error)
        self.assertIn('timed out', transcript.failure_reason.lower())


class AdversarialEvaluatorPhaseTwoTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluate_transcript_normalizes_rules_failure_modes_and_goal_truth(self):
        llm = FakeLLMProvider(
            json_responses=[
                {
                    'verdict': 'HARD_FAIL',
                    'failure_modes': ['did not answer question', 'internal error leak'],
                    'reasoning': 'The bot deflected and surfaced an internal failure.',
                    'goal_achieved': False,
                    'goal_verdicts': [
                        {'goal_id': 'question_answered', 'achieved': False, 'reasoning': 'It never answered.'},
                        {'goal_id': 'invented_goal', 'achieved': True, 'reasoning': 'hallucinated'},
                    ],
                    'rule_compliance': [
                        {
                            'rule_id': 'answer_relevant_to_question',
                            'status': 'FOLLOWED',
                            'evidence': 'The response was about the question topic.',
                        },
                        {
                            'rule_id': 'acknowledge_user_question',
                            'status': 'NOT_APPLICABLE',
                            'evidence': 'The bot never received a direct question.',
                        },
                        {
                            'rule_id': 'hallucinated_rule',
                            'status': 'VIOLATED',
                            'evidence': 'Judge invented this.',
                        },
                    ],
                }
            ]
        )
        config = AdversarialConfig(
            version=5,
            goals=[_goal('question_answered', 'Question Answered')],
            traits=[],
            rules=[
                AdversarialRule(
                    rule_id='answer_relevant_to_question',
                    section='Question Answering',
                    rule_text='Answer the user question directly.',
                    goal_ids=['question_answered'],
                    evaluation_scopes=['adversarial'],
                ),
                AdversarialRule(
                    rule_id='acknowledge_user_question',
                    section='Question Answering',
                    rule_text='Acknowledge the user question.',
                    goal_ids=['question_answered'],
                    evaluation_scopes=['adversarial'],
                ),
            ],
        )
        evaluator = AdversarialEvaluator(llm_provider=llm, config=config)
        transcript = ConversationTranscript(
            turns=[
                ConversationTurn(
                    turn_number=1,
                    user_message='What are high-fiber foods?',
                    bot_response='I can help you log meals.',
                )
            ],
            goal_achieved=True,
            total_turns=1,
            goals_attempted=['question_answered'],
            goals_completed=['question_answered'],
            goal_transitions=[GoalTransition(goal_id='question_answered', event='started', at_turn=1)],
            transport=TransportFacts(had_empty_final_assistant_message=False),
            simulator=SimulatorState(
                goals_attempted=['question_answered'],
                goals_completed=['question_answered'],
                goal_transitions=[GoalTransition(goal_id='question_answered', event='started', at_turn=1)],
                stop_reason='goal_complete',
            ),
        )

        with self.assertLogs('app.services.evaluators.adversarial_evaluator', level='WARNING') as logs:
            evaluation = await evaluator.evaluate_transcript(
                test_case=_test_case(['question_answered']),
                transcript=transcript,
            )

        self.assertFalse(evaluation.goal_achieved)
        self.assertEqual(evaluation.goal_verdicts[0].goal_id, 'question_answered')
        self.assertFalse(evaluation.goal_verdicts[0].achieved)
        self.assertEqual(
            [mode for mode in evaluation.failure_modes],
            ['DID_NOT_ANSWER_QUESTION', 'USER_VISIBLE_INTERNAL_ERROR'],
        )

        by_rule = {item.rule_id: item for item in evaluation.rule_compliance}
        self.assertEqual(sorted(by_rule.keys()), ['acknowledge_user_question', 'answer_relevant_to_question'])
        self.assertEqual(by_rule['answer_relevant_to_question'].status, 'FOLLOWED')
        self.assertTrue(by_rule['answer_relevant_to_question'].followed)
        self.assertEqual(by_rule['acknowledge_user_question'].status, 'NOT_APPLICABLE')
        self.assertIsNone(by_rule['acknowledge_user_question'].followed)
        self.assertTrue(any('hallucinated_rule' in entry for entry in logs.output))

        prompt = llm.generate_json_calls[0]['prompt']
        self.assertIn('### RAW CONVERSATION TRANSCRIPT', prompt)
        self.assertIn('### DETERMINISTIC SYSTEM FACTS', prompt)
        self.assertIn('### SIMULATOR STATE (DEBUG ONLY)', prompt)
        self.assertIn('not authoritative', prompt.lower())


class AdversarialConfigPhaseThreeTests(unittest.TestCase):
    def test_default_config_includes_question_answered_and_cross_goal_rules(self):
        config = get_default_config()
        question_rule_ids = {rule.rule_id for rule in config.prompt_rules_for_goals(['question_answered'])}
        meal_rule_ids = {rule.rule_id for rule in config.prompt_rules_for_goals(['meal_logged'])}

        self.assertTrue(
            {
                'answer_relevant_to_question',
                'answer_substantive_not_deflective',
                'no_capability_loop',
                'acknowledge_user_question',
                'no_user_visible_internal_error',
                'no_hallucinated_system_state',
                'no_stale_context_replay',
                'no_internal_error_leak',
                'maintain_conversational_state_across_goal_transitions',
            }.issubset(question_rule_ids)
        )
        self.assertIn('ask_time_if_missing', meal_rule_ids)
        self.assertIn('maintain_conversational_state_across_goal_transitions', meal_rule_ids)

    def test_v4_to_v5_migration_backfills_new_phase_three_rules(self):
        from app.services.evaluators import adversarial_config as config_module

        migrated = config_module._migrate_v4_to_v5(
            {
                'version': 4,
                'goals': [goal.model_dump() for goal in get_default_config().goals],
                'traits': [],
                'rules': [
                    {
                        'rule_id': 'ask_time_if_missing',
                        'section': 'Time Validation Instructions',
                        'rule_text': 'Ask for time when it is missing.',
                        'goal_ids': ['meal_logged'],
                        'evaluation_scopes': ['adversarial'],
                    }
                ],
            }
        )

        migrated_rule_ids = {rule['rule_id'] for rule in migrated['rules']}
        self.assertEqual(migrated['version'], config_module.CURRENT_VERSION)
        self.assertIn('answer_relevant_to_question', migrated_rule_ids)
        self.assertIn('maintain_conversational_state_across_goal_transitions', migrated_rule_ids)


class CanonicalPersistencePhaseFourTests(unittest.TestCase):
    def test_canonical_case_prefers_judge_truth_and_flags_contradictions(self):
        canonical = build_canonical_adversarial_case(
            {
                'test_case': {
                    'goal_flow': ['meal_logged', 'question_answered'],
                    'difficulty': 'HARD',
                    'active_traits': ['ambiguous_quantity'],
                    'synthetic_input': 'Log breakfast and then answer a question',
                },
                'transcript': {
                    'turns': [{'turn_number': 1, 'user_message': 'hi', 'bot_response': 'hello'}],
                    'total_turns': 1,
                    'goal_achieved': True,
                    'goals_completed': ['meal_logged'],
                    'goals_abandoned': [],
                    'failure_reason': '',
                    'transport': {
                        'had_stream_error': True,
                        'stream_errors': ['summary missing'],
                        'had_partial_response': True,
                    },
                    'simulator': {
                        'goal_achieved': True,
                        'goal_abandoned': False,
                        'goals_attempted': ['meal_logged', 'question_answered'],
                        'goals_completed': ['meal_logged'],
                        'goals_abandoned': [],
                        'goal_transitions': [],
                        'stop_reason': 'goal_complete',
                        'failure_reason': '',
                    },
                },
                'verdict': 'HARD FAIL',
                'goal_achieved': False,
                'goal_verdicts': [
                    {'goal_id': 'meal_logged', 'achieved': True, 'reasoning': 'Meal logged.'},
                    {'goal_id': 'question_answered', 'achieved': False, 'reasoning': 'Question ignored.'},
                ],
                'rule_compliance': [
                    {'rule_id': 'no_stale_context_replay', 'section': 'Cross-Goal', 'status': 'VIOLATED', 'evidence': 'Stale replay'}
                ],
                'failure_modes': ['HALLUCINATED_SYSTEM_STATE'],
                'reasoning': 'The bot replayed stale context and missed the second goal.',
            },
            row_goal_achieved=True,
            row_verdict='HARD FAIL',
            row_goal_flow=['meal_logged', 'question_answered'],
            row_active_traits=['ambiguous_quantity'],
            row_total_turns=1,
            contract_snapshot={
                'version': 5,
                'flow_mode': 'multi',
                'goals': [{'id': 'meal_logged'}, {'id': 'question_answered'}],
                'traits': [{'id': 'ambiguous_quantity'}],
                'rules': [{'rule_id': 'no_stale_context_replay'}],
            },
        )

        self.assertFalse(canonical['judge']['goalAchieved'])
        self.assertTrue(canonical['derived']['hasContradiction'])
        self.assertIn('simulator_goal_vs_judge_goal', canonical['derived']['contradictionTypes'])
        self.assertIn('transport_failure_without_judge_failure_mode', canonical['derived']['contradictionTypes'])
        self.assertTrue(canonical['derived']['isInfraFailure'])
        self.assertTrue(canonical['derived']['isRetryable'])
        self.assertEqual(canonical['contract']['version'], 5)
        self.assertEqual(canonical['contract']['ruleIds'], ['no_stale_context_replay'])

    def test_api_enrichment_keeps_legacy_fields_but_exposes_canonical_case(self):
        enriched = enrich_adversarial_result_for_api(
            {
                'test_case': {'goal_flow': ['question_answered'], 'difficulty': 'MEDIUM', 'active_traits': [], 'synthetic_input': 'What is fiber?'},
                'transcript': {'turns': [], 'total_turns': 0, 'goal_achieved': True, 'failure_reason': ''},
                'goal_achieved': False,
                'goal_verdicts': [{'goal_id': 'question_answered', 'achieved': False}],
                'rule_compliance': [],
                'failure_modes': ['DID_NOT_ANSWER_QUESTION'],
                'verdict': 'HARD FAIL',
            },
            row_goal_achieved=True,
            row_verdict='PASS',
            row_goal_flow=['question_answered'],
            row_active_traits=[],
            row_total_turns=0,
        )

        self.assertIn('canonical_case', enriched)
        self.assertFalse(enriched['goal_achieved'])
        self.assertEqual(enriched['verdict'], 'HARD FAIL')
        self.assertEqual(enriched['failure_modes'], ['DID_NOT_ANSWER_QUESTION'])
        self.assertFalse(enriched['canonical_case']['derived']['isRetryable'])


class AnalyticsPhaseFourTests(unittest.TestCase):
    def test_adversarial_aggregator_counts_all_goal_verdicts_and_infra_failures(self):
        evaluations = [
            SimpleNamespace(
                id=1,
                verdict='PASS',
                difficulty='HARD',
                goal_flow=['meal_logged', 'question_answered'],
                active_traits=[],
                total_turns=4,
                result={
                    'canonical_case': {
                        'facts': {'transcript': {'turns': []}},
                        'judge': {
                            'verdict': 'PASS',
                            'goalAchieved': True,
                            'goalVerdicts': [
                                {'goalId': 'meal_logged', 'achieved': True},
                                {'goalId': 'question_answered', 'achieved': True},
                            ],
                            'ruleOutcomes': [
                                {'ruleId': 'answer_relevant_to_question', 'status': 'FOLLOWED', 'evidence': 'ok', 'section': 'QnA'},
                            ],
                            'failureModes': [],
                            'reasoning': 'ok',
                        },
                        'derived': {'isInfraFailure': False, 'hasContradiction': False, 'contradictionTypes': []},
                    }
                },
            ),
            SimpleNamespace(
                id=2,
                verdict='HARD FAIL',
                difficulty='MEDIUM',
                goal_flow=['question_answered'],
                active_traits=[],
                total_turns=3,
                result={
                    'canonical_case': {
                        'facts': {'transcript': {'turns': []}},
                        'judge': {
                            'verdict': 'HARD_FAIL',
                            'goalAchieved': False,
                            'goalVerdicts': [
                                {'goalId': 'question_answered', 'achieved': False},
                            ],
                            'ruleOutcomes': [
                                {'ruleId': 'answer_relevant_to_question', 'status': 'VIOLATED', 'evidence': 'bad', 'section': 'QnA'},
                            ],
                            'failureModes': ['DID_NOT_ANSWER_QUESTION'],
                            'reasoning': 'bad',
                        },
                        'derived': {'isInfraFailure': False, 'hasContradiction': False, 'contradictionTypes': []},
                    }
                },
            ),
            SimpleNamespace(
                id=3,
                verdict=None,
                difficulty='EASY',
                goal_flow=['meal_logged'],
                active_traits=[],
                total_turns=1,
                result={
                    'error': 'timeout',
                    'canonical_case': {
                        'facts': {'transcript': {'turns': []}},
                        'judge': {
                            'verdict': None,
                            'goalAchieved': False,
                            'goalVerdicts': [{'goalId': 'meal_logged', 'achieved': False}],
                            'ruleOutcomes': [],
                            'failureModes': [],
                            'reasoning': '',
                        },
                        'derived': {'isInfraFailure': True, 'hasContradiction': False, 'contradictionTypes': []},
                    }
                },
            ),
        ]

        aggregator = AdversarialAggregator(evaluations, {})
        breakdown = aggregator.compute_adversarial_breakdown()
        distributions = aggregator.compute_distributions()

        by_goal = {row.goal: row for row in breakdown.by_goal}
        self.assertEqual(by_goal['meal_logged'].total, 2)
        self.assertEqual(by_goal['meal_logged'].passed, 1)
        self.assertEqual(by_goal['question_answered'].total, 2)
        self.assertEqual(by_goal['question_answered'].passed, 1)
        self.assertEqual(distributions.adversarial['ERROR'], 1)



if __name__ == '__main__':
    unittest.main()
