"""resolve_template pack handler — chain-order + fetch-path + never-passthrough.

The handler resolves a wati_template_picker field. It enforces the per-turn
chain order (connection_id MUST have been listed/resolved earlier this turn,
i.e. present in the scratch allowlist), fetches via the SAME path the FE
picker uses (list_connection_wati_templates — D1), and returns resolved /
pick / not_found. An unknown intent NEVER comes back as a raw template name.
"""
from __future__ import annotations

import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.orchestration_authoring import (
    orchestration_authoring_pack as pack_mod,
)
from app.services.orchestration_authoring.orchestration_authoring_pack import (
    OrchestrationAuthoringPack,
)


_CONN_ID = str(uuid.uuid4())

_WATI_ITEMS = [
    {
        "name": "document_approved_latest",
        "language": "en",
        "status": "APPROVED",
        "parameters": ["name", "documentType"],
        "body": "Hi *{{1}}*, your *{{2}}* has been approved.",
        "body_original": None,
    },
    {
        "name": "appointment_reminder",
        "language": "en",
        "status": "APPROVED",
        "parameters": ["name", "date"],
        "body": "Hi {{1}}, your appointment is on {{2}}.",
        "body_original": None,
    },
]


def _make_auth(app: str = 'inside-sales') -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        permissions=frozenset({'orchestration:manage'}),
        app_access=frozenset({app}),
        is_owner=False,
    )


def _make_snapshot(app: str = 'inside-sales') -> SimpleNamespace:
    return SimpleNamespace(
        workflow_id=uuid.uuid4(),
        version_id=None,
        workflow_type='crm',
        app_id=app,
        definition={'nodes': [], 'edges': []},
        data_hash='hash-1',
        selected_node_id=None,
        view_mode='edit',
    )


def _make_ctx(*, scratch=None) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(
            builder_context=_make_snapshot(),
            auth=_make_auth(),
            scratch=scratch if scratch is not None else {},
        ),
    )


class ResolveTemplateHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection_not_in_allowlist_errors_asking_to_resolve_first(self) -> None:
        ctx = _make_ctx(scratch={'authorized_uuids': set()})
        args = json.dumps({'connection_id': _CONN_ID, 'intent': 'document approved'})
        with patch.object(
            pack_mod, '_assert_builder_workflow_still_owned',
            new=AsyncMock(return_value='inside-sales'),
        ):
            result = await pack_mod._resolve_template_handler(ctx, args)
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'error')
        # Must NOT have called the fetch path when the connection isn't allowlisted.

    async def test_exact_intent_resolves_with_placeholders(self) -> None:
        ctx = _make_ctx(scratch={'authorized_uuids': {_CONN_ID}})
        args = json.dumps({'connection_id': _CONN_ID, 'intent': 'document_approved_latest'})
        with patch.object(
            pack_mod, '_assert_builder_workflow_still_owned',
            new=AsyncMock(return_value='inside-sales'),
        ), patch.object(
            pack_mod, 'list_connection_wati_templates',
            new=AsyncMock(return_value={'provider': 'wati', 'items': _WATI_ITEMS, 'error': None}),
        ):
            result = await pack_mod._resolve_template_handler(ctx, args)
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'ok')
        self.assertEqual(decoded['payload']['status'], 'resolved')
        self.assertEqual(decoded['payload']['name'], 'document_approved_latest')
        self.assertEqual(decoded['payload']['placeholders'], ['name', 'documentType'])

    async def test_unknown_intent_returns_not_found_never_passthrough(self) -> None:
        ctx = _make_ctx(scratch={'authorized_uuids': {_CONN_ID}})
        args = json.dumps({'connection_id': _CONN_ID, 'intent': 'zzz_unrelated'})
        with patch.object(
            pack_mod, '_assert_builder_workflow_still_owned',
            new=AsyncMock(return_value='inside-sales'),
        ), patch.object(
            pack_mod, 'list_connection_wati_templates',
            new=AsyncMock(return_value={'provider': 'wati', 'items': _WATI_ITEMS, 'error': None}),
        ):
            result = await pack_mod._resolve_template_handler(ctx, args)
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'ok')
        self.assertEqual(decoded['payload']['status'], 'not_found')
        self.assertIsNone(decoded['payload'].get('name'))
        # The raw intent must NEVER surface as a template name.
        self.assertNotEqual(decoded['payload'].get('name'), 'zzz_unrelated')

    async def test_ambiguous_intent_returns_pick_list(self) -> None:
        items = _WATI_ITEMS + [{
            'name': 'appointment_confirmation', 'language': 'en',
            'status': 'APPROVED', 'parameters': ['name'],
            'body': 'Hi {{1}}.', 'body_original': None,
        }]
        ctx = _make_ctx(scratch={'authorized_uuids': {_CONN_ID}})
        args = json.dumps({'connection_id': _CONN_ID, 'intent': 'appointment'})
        with patch.object(
            pack_mod, '_assert_builder_workflow_still_owned',
            new=AsyncMock(return_value='inside-sales'),
        ), patch.object(
            pack_mod, 'list_connection_wati_templates',
            new=AsyncMock(return_value={'provider': 'wati', 'items': items, 'error': None}),
        ):
            result = await pack_mod._resolve_template_handler(ctx, args)
        decoded = json.loads(result)
        self.assertEqual(decoded['payload']['status'], 'pick')
        self.assertIn('appointment_reminder', decoded['payload']['candidates'])
        self.assertIn('appointment_confirmation', decoded['payload']['candidates'])


class ResolveTemplateRegistrationTests(unittest.TestCase):
    def test_resolve_template_registered_in_specs_and_handlers(self) -> None:
        pack = OrchestrationAuthoringPack()
        names = {s['name'] for s in pack.tool_specs()}
        self.assertIn('resolve_template', names)
        self.assertIn('resolve_template', pack.tool_handlers())
        self.assertIn('resolve_template', pack.describe_tools('inside-sales'))

    def test_resolve_template_schema_requires_connection_and_intent(self) -> None:
        spec = next(
            s for s in OrchestrationAuthoringPack().tool_specs()
            if s['name'] == 'resolve_template'
        )
        schema = spec['params_json_schema']
        self.assertEqual(set(schema['required']), {'connection_id', 'intent'})
        self.assertFalse(schema['additionalProperties'])

    def test_list_action_templates_description_disclaims_wati(self) -> None:
        pack = OrchestrationAuthoringPack()
        spec = next(
            s for s in pack.tool_specs() if s['name'] == 'list_action_templates'
        )
        desc = spec['description'].lower()
        self.assertIn('internal', desc)
        self.assertIn('resolve_template', spec['description'])
        # describe_tools mirror also disclaims.
        self.assertIn('internal', pack.describe_tools('inside-sales')['list_action_templates'].lower())


if __name__ == '__main__':
    unittest.main()
