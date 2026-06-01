"""apply_patch rejects a whatsapp template_name the agent did not resolve.

§3 invariant: the LLM never invents a template. resolve_template records its
real names into the SAME per-turn allowlist that already gates connection_id
(template_name is just another _TOOL_RESOLVED_REFERENCE_KEYS entry), so a
phantom template can never reach a node config even if the agent skips the tool.
"""
from __future__ import annotations

import json
import unittest
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from app.services.orchestration_authoring.builder_snapshot import BuilderSnapshot
from app.services.orchestration_authoring.orchestration_authoring_pack import (
    _apply_patch_handler,
)

_CONN = '11111111-1111-1111-1111-111111111111'


def _auth() -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=uuid.uuid4(), user_id=uuid.uuid4(),
        permissions=frozenset({'orchestration:manage'}),
        app_access=frozenset({'inside-sales'}), is_owner=False,
    )


def _snapshot() -> BuilderSnapshot:
    return BuilderSnapshot(
        workflow_id=uuid.uuid4(), version_id=None, workflow_type='crm',
        app_id='inside-sales', definition={'nodes': [], 'edges': []},
        data_hash='h', selected_node_id=None, view_mode='edit',
    )


def _ctx(scratch: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(context=SimpleNamespace(
        builder_context=_snapshot(), auth=_auth(), scratch=scratch))


def _whatsapp_op(template_name: str) -> str:
    return json.dumps({'ops_json': json.dumps([{
        'op': 'add_node', 'node_id': 'send',
        'payload': {'node_type': 'messaging.send_whatsapp_template',
                    'config': {'connection_id': _CONN, 'template_name': template_name}},
    }]), 'rationale': 't'})


async def _call(ctx: SimpleNamespace, args: str) -> dict:
    with patch(
        'app.services.orchestration_authoring.orchestration_authoring_pack.'
        '_assert_builder_workflow_still_owned',
        new=AsyncMock(return_value='inside-sales'),
    ):
        return json.loads(await _apply_patch_handler(ctx, args))


class TemplateGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_unresolved_template_is_rejected(self) -> None:
        ctx = _ctx({'authorized_uuids': {_CONN}})  # no template resolved this turn
        decoded = await _call(ctx, _whatsapp_op('document_latest_approved'))
        self.assertEqual(decoded['status'], 'error', msg=decoded)
        self.assertEqual(decoded['meta']['reason_code'], 'UUID_NOT_AUTHORIZED')
        self.assertIn('template_name', decoded['summary'])

    async def test_resolved_template_is_allowed(self) -> None:
        # One allowlist: resolve_template drops its real name into authorized_uuids
        # alongside the connection id, so apply_patch accepts it.
        ctx = _ctx({'authorized_uuids': {_CONN, 'document_approved_latest'}})
        decoded = await _call(ctx, _whatsapp_op('document_approved_latest'))
        self.assertEqual(decoded['status'], 'ok', msg=decoded)


if __name__ == '__main__':
    unittest.main()
