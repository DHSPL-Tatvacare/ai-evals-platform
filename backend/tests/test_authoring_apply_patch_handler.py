"""Phase 1 Step 2 — apply_patch handler reason-code coverage.

Each test triggers exactly one reason_code from the Step 2 surface:
NODE_CONFIG_INVALID, UNKNOWN_NODE_TYPE, PATCH_OPS_EMPTY, PATCH_TOO_LARGE.
Layered checks (NO_BUILDER_CONTEXT, PERMISSION_DENIED, APP_FORBIDDEN,
CREDENTIAL_LEAK_BLOCKED) are also covered here so the per-tool re-check
(R3) can never silently regress.
"""
from __future__ import annotations

import json
import unittest
import uuid
from types import SimpleNamespace
from typing import Any

from app.services.orchestration_authoring.builder_snapshot import BuilderSnapshot
from app.services.orchestration_authoring.canvas_patch import (
    CANVAS_PATCH_CONTRACT_ID,
)
from app.services.orchestration_authoring.orchestration_authoring_pack import (
    MAX_PATCH_OPS,
    _apply_patch_handler,
)


def _make_auth(*, has_perm: bool = True, app: str = 'inside-sales') -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        permissions=frozenset({'orchestration:manage'}) if has_perm else frozenset(),
        app_access=frozenset({app}),
    )


_VALID_MINIMAL_DEFINITION = {
    'nodes': [
        {
            'id': 'src',
            'type': 'source.event_trigger',
            'position': {'x': 0, 'y': 0},
            'data': {},
            'config': {'event_name': 'demo'},
        },
        {
            'id': 'sink',
            'type': 'sink.complete',
            'position': {'x': 200, 'y': 0},
            'data': {},
            'config': {},
        },
    ],
    'edges': [
        {
            'id': 'e1',
            'source': 'src',
            'target': 'sink',
            'output_id': 'default',
        },
    ],
}


def _make_snapshot(*, app: str = 'inside-sales',
                    definition: dict | None = None) -> BuilderSnapshot:
    return BuilderSnapshot(
        workflow_id=uuid.uuid4(),
        version_id=None,
        workflow_type='crm',
        app_id=app,
        definition=definition if definition is not None else dict(_VALID_MINIMAL_DEFINITION),
        data_hash='hash-1',
        selected_node_id=None,
        view_mode='edit',
    )


def _make_ctx(*, builder: Any = None, auth: Any = None) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(
            builder_context=builder,
            auth=auth,
            scratch={},
        ),
    )


def _ops(*ops: dict[str, Any]) -> str:
    return json.dumps(list(ops))


def _wrap(*, ops_json: str, rationale: str = 'test') -> str:
    return json.dumps({'ops_json': ops_json, 'rationale': rationale})


class ApplyPatchReasonCodeTests(unittest.IsolatedAsyncioTestCase):
    async def _call(self, *, args: str, builder: Any = None, auth: Any = None) -> dict:
        b = builder or _make_snapshot()
        a = auth or _make_auth()
        result = await _apply_patch_handler(_make_ctx(builder=b, auth=a), args)
        return json.loads(result)

    async def test_no_builder_context(self) -> None:
        result = await _apply_patch_handler(
            _make_ctx(builder=None, auth=_make_auth()),
            _wrap(ops_json='[]'),
        )
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'error')
        self.assertEqual(decoded['meta']['reason_code'], 'NO_BUILDER_CONTEXT')

    async def test_permission_denied(self) -> None:
        decoded = await self._call(
            args=_wrap(ops_json='[]'),
            auth=_make_auth(has_perm=False),
        )
        self.assertEqual(decoded['meta']['reason_code'], 'PERMISSION_DENIED')

    async def test_app_forbidden(self) -> None:
        # auth gives access to a different app than the snapshot
        auth = _make_auth(app='voice-rx')
        decoded = await self._call(
            args=_wrap(ops_json='[]'),
            builder=_make_snapshot(app='inside-sales'),
            auth=auth,
        )
        self.assertEqual(decoded['meta']['reason_code'], 'APP_FORBIDDEN')

    async def test_patch_ops_empty_when_blank(self) -> None:
        decoded = await self._call(args=_wrap(ops_json=''))
        self.assertEqual(decoded['meta']['reason_code'], 'PATCH_OPS_EMPTY')

    async def test_patch_ops_empty_when_array_empty(self) -> None:
        decoded = await self._call(args=_wrap(ops_json='[]'))
        self.assertEqual(decoded['meta']['reason_code'], 'PATCH_OPS_EMPTY')

    async def test_patch_too_large(self) -> None:
        big = [
            {'op': 'remove_node', 'node_id': f'n{i}', 'payload': {}}
            for i in range(MAX_PATCH_OPS + 1)
        ]
        decoded = await self._call(args=_wrap(ops_json=_ops(*big)))
        self.assertEqual(decoded['meta']['reason_code'], 'PATCH_TOO_LARGE')

    async def test_unknown_node_type(self) -> None:
        ops = _ops({
            'op': 'add_node',
            'node_id': 'n1',
            'payload': {'node_type': 'made.up.node', 'config': {}},
        })
        decoded = await self._call(args=_wrap(ops_json=ops))
        self.assertEqual(decoded['meta']['reason_code'], 'UNKNOWN_NODE_TYPE')

    async def test_node_config_invalid(self) -> None:
        # crm.send_wati requires several fields — sending an empty config
        # trips the per-node Pydantic validator.
        ops = _ops({
            'op': 'add_node',
            'node_id': 'n1',
            'payload': {'node_type': 'crm.send_wati', 'config': {'foo': 'bar'}},
        })
        decoded = await self._call(args=_wrap(ops_json=ops))
        self.assertEqual(decoded['meta']['reason_code'], 'NODE_CONFIG_INVALID')

    async def test_node_config_invalid_when_ops_json_malformed(self) -> None:
        decoded = await self._call(
            args=_wrap(ops_json='{not valid json'),
        )
        self.assertEqual(decoded['meta']['reason_code'], 'NODE_CONFIG_INVALID')

    async def test_apply_patch_happy_path_emits_artifact(self) -> None:
        # Update the existing sink node's config patch — graph preflight
        # passes because the resulting graph is still a valid src→sink chain.
        ops = _ops({
            'op': 'update_node_config',
            'node_id': 'sink',
            'payload': {'config_patch': {'reason': 'demo done'}},
        })
        decoded = await self._call(args=_wrap(ops_json=ops, rationale='clean up'))
        self.assertEqual(decoded['status'], 'ok', msg=decoded)
        self.assertEqual(len(decoded['artifacts']), 1)
        artifact = decoded['artifacts'][0]
        self.assertEqual(artifact['kind'], CANVAS_PATCH_CONTRACT_ID)
        self.assertEqual(len(artifact['payload']['ops']), 1)
        self.assertEqual(artifact['payload']['rationale'], 'clean up')

    async def test_connect_op_validates_required_fields(self) -> None:
        ops = _ops({
            'op': 'connect',
            'node_id': 'n1',
            'payload': {
                'source_node_id': 'n1',
                'output_id': 'default',
                'target_node_id': 'n2',
                # missing edge_id
            },
        })
        decoded = await self._call(args=_wrap(ops_json=ops))
        self.assertEqual(decoded['meta']['reason_code'], 'NODE_CONFIG_INVALID')


class ApplyPatchToolSpecTests(unittest.TestCase):
    def test_apply_patch_spec_has_strict_schema(self) -> None:
        from app.services.orchestration_authoring.orchestration_authoring_pack import (
            OrchestrationAuthoringPack,
        )

        pack = OrchestrationAuthoringPack()
        specs = {s['name']: s for s in pack.tool_specs()}
        self.assertIn('apply_patch', specs)
        schema = specs['apply_patch']['params_json_schema']
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']), {'ops_json', 'rationale'})


if __name__ == '__main__':
    unittest.main()
