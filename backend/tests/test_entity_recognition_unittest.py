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

    async def test_recognize_entities_carries_forward_prior_resolved_entities(self):
        provider = _FakeProvider(
            {
                'is_platform_query': True,
                'needs_resolution': False,
                'out_of_scope_reason': None,
                'entities': [],
            }
        )

        with patch(
            'app.services.chat_engine.entity_recognition._create_entity_recognition_provider',
            new=AsyncMock(return_value=provider),
        ):
            result = await recognize_entities(
                question='Now show only that thread',
                provider='openai',
                model='gpt-4o-mini',
                tenant_id='tenant-1',
                user_id='user-1',
                entity_registry=[{'name': 'threadId', 'description': 'Conversation thread identifier'}],
                scratchpad={
                    'resolved_entities': {
                        'threadId': {
                            'matches': [
                                {
                                    'value': 'thread-42',
                                    'label': 'Thread 42',
                                }
                            ],
                        }
                    }
                },
            )

        self.assertEqual(len(result.entities), 1)
        self.assertEqual(result.entities[0].type, 'threadId')
        self.assertEqual(result.entities[0].text, 'thread-42')


if __name__ == '__main__':
    unittest.main()
