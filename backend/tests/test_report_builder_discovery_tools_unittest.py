from __future__ import annotations

import unittest
import uuid
from unittest.mock import AsyncMock, patch

from app.auth import AuthContext
from app.services.report_builder import tool_handlers


class _Result:
    def __init__(self, *, rows=None, scalar_value=None, first_row=None):
        self._rows = rows or []
        self._scalar_value = scalar_value
        self._first_row = first_row

    def all(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar_value

    def first(self):
        return self._first_row


class ReportBuilderDiscoveryToolTests(unittest.IsolatedAsyncioTestCase):
    def _auth(self) -> AuthContext:
        return AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            email='user@example.com',
            role_id=uuid.uuid4(),
            is_owner=True,
            permissions=frozenset(),
            app_access=frozenset({'inside-sales'}),
        )

    async def test_handle_discover_uses_session_cache(self):
        cached = {
            'status': 'ok',
            'app_id': 'inside-sales',
            'dimensions': [{'name': 'agent', 'values': []}],
            'metrics': [{'name': 'pass_rate', 'description': 'Pass rate'}],
            'time_range': {},
            'volume': {},
        }

        result = await tool_handlers.handle_discover(
            db=AsyncMock(),
            auth=self._auth(),
            app_id='inside-sales',
            session={'scratchpad': {'discovery': cached}},
        )

        # Phase 2: envelope shape — cached body sits under ``envelope.payload``.
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['payload']['app_id'], 'inside-sales')
        self.assertTrue(result['payload']['cache_hit'])

    async def test_handle_lookup_resolves_dimension_values(self):
        db = AsyncMock()
        db.execute.return_value = _Result(rows=[('Pareekshith Bompally', 12), ('Vicky Yadav', 9)])
        semantic_model = {
            'tables': {
                'analytics_eval_facts': {
                    'access_control': {'tenant_column': 'tenant_id', 'app_column': 'app_id'},
                },
            },
            'dimensions': [
                {
                    'name': 'agent',
                    'table': 'analytics_eval_facts',
                    'expression': "context->>'agent'",
                },
            ],
        }

        with patch(
            'app.services.report_builder.tool_handlers._load_active_semantic_model',
            new=AsyncMock(return_value=semantic_model),
        ):
            result = await tool_handlers.handle_lookup(
                dimension='agent',
                search='pareek',
                db=db,
                auth=self._auth(),
                app_id='inside-sales',
            )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['payload']['dimension'], 'agent')
        self.assertEqual(result['payload']['values'][0]['value'], 'Pareekshith Bompally')

    async def test_handle_discover_builds_dimension_metric_and_volume_payload(self):
        db = AsyncMock()
        db.execute.side_effect = [
            _Result(rows=[('inbound', 7), ('outbound', 3)]),
            _Result(scalar_value=4),
            _Result(scalar_value=10),
            _Result(first_row=('2026-01-01', '2026-04-01')),
        ]
        semantic_model = {
            'tables': {
                'analytics_run_facts': {
                    'access_control': {'tenant_column': 'tenant_id', 'app_column': 'app_id'},
                },
                'analytics_eval_facts': {
                    'access_control': {'tenant_column': 'tenant_id', 'app_column': 'app_id'},
                },
            },
            'dimensions': [
                {
                    'name': 'direction',
                    'table': 'analytics_eval_facts',
                    'expression': "context->>'direction'",
                    'description': 'Inbound or outbound',
                },
            ],
            'metrics': {
                'pass_rate': {
                    'description': 'Pass rate',
                },
            },
        }

        with patch(
            'app.services.report_builder.tool_handlers._load_active_semantic_model',
            new=AsyncMock(return_value=semantic_model),
        ), patch(
            'app.services.chat_engine.sql_agent.load_app_config',
            new=AsyncMock(return_value={
                'chat': {
                    'dataSurfaces': [
                        {
                            'key': 'logs',
                            'description': 'Raw logs',
                            'source': 'api_logs',
                            'entityFieldMap': {'thread_id': 'thread_id'},
                            'fields': ['thread_id', 'response'],
                            'defaultLimit': 10,
                        },
                    ],
                    'entityResolvers': [
                        {
                            'key': 'thread-id',
                            'entityType': 'thread_id',
                            'source': 'api_logs',
                            'field': 'thread_id',
                        },
                    ],
                },
            }),
        ):
            result = await tool_handlers.handle_discover(
                db=db,
                auth=self._auth(),
                app_id='inside-sales',
                session={'scratchpad': {}},
            )

        # Phase 2 envelope — discovery data lives under ``envelope.payload``.
        # Surfaces are sourced from the app manifest (canonical), entity
        # resolvers come from the mocked ``app_config.chat.entityResolvers``.
        self.assertEqual(result['status'], 'ok')
        body = result['payload']
        self.assertEqual(body['dimensions'][0]['name'], 'direction')
        self.assertEqual(body['metrics'][0]['name'], 'pass_rate')
        self.assertEqual(body['volume']['runs'], 4)
        self.assertEqual(body['volume']['evaluations'], 10)
        self.assertEqual(body['time_range']['earliest'], '2026-01-01')
        # Manifest is the source of truth for data surfaces (see CLAUDE.md).
        surface_keys = [s['key'] for s in body['surfaces']]
        self.assertIn('logs', surface_keys)
        self.assertEqual(body['entity_types'], ['thread_id'])


if __name__ == '__main__':
    unittest.main()
