from __future__ import annotations

import unittest

from app.services.chat_engine.entity_registry import load_entity_registry


class EntityRegistryTests(unittest.TestCase):
    def test_load_entity_registry_merges_seeded_resolvers_and_dimensions(self):
        registry = load_entity_registry(
            'inside-sales',
            app_config={
                'chat': {
                    'entityTypes': [
                        {
                            'name': 'agent',
                            'description': 'Sales agent',
                            'examples': ['Pareekshith Bompally'],
                        },
                        {
                            'name': 'thread_id',
                            'description': 'Thread identifier',
                            'examples': ['thread-123'],
                        },
                    ],
                    'entityResolvers': [
                        {
                            'entityType': 'thread_id',
                            'description': 'Resolve thread IDs from logs',
                            'source': 'api_logs',
                        },
                        {
                            'entityType': 'campaign',
                            'description': 'Resolve campaign names',
                            'source': 'semantic_dimension',
                        },
                    ],
                }
            },
            semantic_model={
                'dimensions': [
                    {
                        'name': 'campaign',
                        'description': 'Campaign dimension',
                        'table': 'analytics_eval_facts',
                        'expression': "context->>'campaign'",
                    },
                    {
                        'name': 'callDisposition',
                        'description': 'Disposition dimension',
                        'table': 'analytics_eval_facts',
                        'expression': "context->>'callDisposition'",
                    },
                ]
            },
        )

        self.assertEqual(
            registry,
            [
                {
                    'name': 'agent',
                    'description': 'Sales agent',
                    'examples': ['Pareekshith Bompally'],
                },
                {
                    'name': 'thread_id',
                    'description': 'Thread identifier',
                    'examples': ['thread-123'],
                },
                {
                    'name': 'campaign',
                    'description': 'Resolve campaign names',
                    'examples': [],
                },
                {
                    'name': 'callDisposition',
                    'description': 'Disposition dimension',
                    'examples': [],
                },
            ],
        )


if __name__ == '__main__':
    unittest.main()
