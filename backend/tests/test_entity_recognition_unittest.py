from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.chat_engine.entity_recognition import recognize_entities


class _FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def generate_json(self, *, prompt, system_prompt, json_schema):
        self.calls.append({'prompt': prompt, 'system_prompt': system_prompt, 'json_schema': json_schema})
        return self.payload


class EntityRecognitionTests(unittest.IsolatedAsyncioTestCase):
    async def test_recognize_entities_classifies_platform_questions(self):
        provider = _FakeProvider(
            {
                'is_platform_query': True,
                'needs_resolution': True,
                'out_of_scope_reason': None,
                'entities': [
                    {'type': 'callDisposition', 'text': 'Interested', 'confidence': 0.94},
                    {'type': 'unknownType', 'text': 'ignored', 'confidence': 0.6},
                ],
            }
        )

        with patch(
            'app.services.chat_engine.entity_recognition._create_entity_recognition_provider',
            new=AsyncMock(return_value=provider),
        ):
            result = await recognize_entities(
                question='Show interested leads this week',
                provider='openai',
                model='gpt-4o-mini',
                tenant_id='tenant-1',
                user_id='user-1',
                entity_registry=[
                    {'name': 'callDisposition', 'description': 'Disposition for a sales call', 'examples': ['Interested']},
                ],
                scratchpad={},
            )

        self.assertTrue(result.is_platform_query)
        self.assertTrue(result.needs_resolution)
        self.assertEqual(len(result.entities), 1)
        self.assertEqual(result.entities[0].type, 'callDisposition')
        self.assertEqual(provider.calls[0]['json_schema']['type'], 'object')

    async def test_recognize_entities_marks_off_topic_questions(self):
        provider = _FakeProvider(
            {
                'is_platform_query': False,
                'needs_resolution': False,
                'out_of_scope_reason': 'The user asked about cricket scores.',
                'entities': [],
            }
        )

        with patch(
            'app.services.chat_engine.entity_recognition._create_entity_recognition_provider',
            new=AsyncMock(return_value=provider),
        ):
            result = await recognize_entities(
                question='Who won the cricket match today?',
                provider='openai',
                model='gpt-4o-mini',
                tenant_id='tenant-1',
                user_id='user-1',
                entity_registry=[],
                scratchpad={},
            )

        self.assertFalse(result.is_platform_query)
        self.assertFalse(result.needs_resolution)
        self.assertEqual(result.entities, [])

    async def test_recognize_entities_uses_previous_turn_context_for_terse_followup(self):
        class _FollowupAwareProvider:
            def __init__(self):
                self.calls = []

            async def generate_json(self, *, prompt, system_prompt, json_schema):
                self.calls.append({'prompt': prompt, 'system_prompt': system_prompt, 'json_schema': json_schema})
                assert 'Previous turn context:' in prompt
                assert 'Show the distribution of rule violations across all evaluation runs as a pie chart.' in prompt
                assert '"result_kind": "chart"' in prompt
                return {
                    'is_platform_query': True,
                    'needs_resolution': False,
                    'out_of_scope_reason': None,
                    'entities': [],
                }

        provider = _FollowupAwareProvider()

        with patch(
            'app.services.chat_engine.entity_recognition._create_entity_recognition_provider',
            new=AsyncMock(return_value=provider),
        ):
            result = await recognize_entities(
                question='I asked for pie chart',
                provider='openai',
                model='gpt-4o-mini',
                tenant_id='tenant-1',
                user_id='user-1',
                entity_registry=[{'name': 'rule', 'description': 'Rule label'}],
                scratchpad={
                    'last_analysis': {
                        'question': 'Show the distribution of rule violations across all evaluation runs as a pie chart.',
                        'row_count': 11,
                        'columns': ['rule', 'violation_count'],
                        'preview_rows': [{'rule': 'Rule A', 'violation_count': 4}],
                        'chart_summary': {'kind': 'chart', 'mark': 'bar'},
                    },
                    'outcomes': [
                        {
                            'tool': 'data_query',
                            'artifact_type': 'chart',
                            'reason_code': None,
                            'counts': {'rows': 11, 'records': 0, 'affected': 0},
                        }
                    ],
                },
            )

        self.assertTrue(result.is_platform_query)
        self.assertEqual(result.entities, [])

    async def test_recognize_entities_drops_app_alias_from_run_name_entity(self):
        provider = _FakeProvider(
            {
                'is_platform_query': True,
                'needs_resolution': True,
                'out_of_scope_reason': None,
                'entities': [
                    {'type': 'run_name', 'text': 'kaira', 'confidence': 0.98},
                    {'type': 'status', 'text': 'PASS', 'confidence': 0.91},
                ],
            }
        )

        with patch(
            'app.services.chat_engine.entity_recognition._create_entity_recognition_provider',
            new=AsyncMock(return_value=provider),
        ):
            result = await recognize_entities(
                question='Show kaira eval runs per status',
                provider='openai',
                model='gpt-4o-mini',
                tenant_id='tenant-1',
                user_id='user-1',
                entity_registry=[
                    {'name': 'run_name', 'description': 'Run name'},
                    {'name': 'status', 'description': 'Status'},
                ],
                scratchpad={},
                app_scope_terms=['kaira', 'kaira bot'],
            )

        self.assertEqual([entity.type for entity in result.entities], ['status'])

    async def test_recognize_entities_keeps_explicit_run_name_intent(self):
        provider = _FakeProvider(
            {
                'is_platform_query': True,
                'needs_resolution': True,
                'out_of_scope_reason': None,
                'entities': [
                    {'type': 'run_name', 'text': 'kaira', 'confidence': 0.98},
                ],
            }
        )

        with patch(
            'app.services.chat_engine.entity_recognition._create_entity_recognition_provider',
            new=AsyncMock(return_value=provider),
        ):
            result = await recognize_entities(
                question='Show runs named kaira',
                provider='openai',
                model='gpt-4o-mini',
                tenant_id='tenant-1',
                user_id='user-1',
                entity_registry=[{'name': 'run_name', 'description': 'Run name'}],
                scratchpad={},
                app_scope_terms=['kaira', 'kaira bot'],
            )

        self.assertEqual(len(result.entities), 1)
        self.assertEqual(result.entities[0].type, 'run_name')


if __name__ == '__main__':
    unittest.main()
