"""A-Step 2 — value-level outcome/event guard in apply_patch.

The per-node Pydantic schema is ``extra='forbid'`` but it cannot know whether
a conditional ``value`` or a wait ``event_name`` is a REAL provider outcome /
event for THIS canvas — that vocabulary is producer-truth, resolved by
``resolve_upstream_variables``. These tests assert apply_patch rejects an
authored conditional/wait that branches on an outcome/event the resolver did
NOT surface (reason_code UNKNOWN_OUTCOME / UNKNOWN_EVENT), and accepts one that
uses a resolved canonical value. The resolver is mocked — no live DB, no live
external API. The guard WRAPS the same resolver A-Step 1 exposed; it never
re-derives vocabulary.
"""
from __future__ import annotations

import json
import unittest
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from app.schemas.orchestration import (
    ResolveUpstreamVariablesResponse,
    UpstreamEvent,
    UpstreamField,
    UpstreamOutcomeEnum,
)
from app.services.orchestration_authoring.builder_snapshot import BuilderSnapshot
from app.services.orchestration_authoring.orchestration_authoring_pack import (
    REASON_CODES,
    _apply_patch_handler,
)


_VOICE_NODE_ID = 'voice-1'
_OUTCOME_FIELD = f'steps.{_VOICE_NODE_ID}.outcome'


def _make_auth(app: str = 'inside-sales') -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        permissions=frozenset({'orchestration:manage'}),
        app_access=frozenset({app}),
        is_owner=False,
    )


def _voice_definition() -> dict:
    """A voice producer already on the canvas; the patch wires a downstream
    conditional / wait against its resolved outcome/event vocabulary."""
    return {
        'nodes': [
            {
                'id': _VOICE_NODE_ID,
                'type': 'voice.place_call',
                'position': {'x': 0, 'y': 0},
                'data': {'label': 'Place call'},
                'config': {},
            },
        ],
        'edges': [],
    }


def _make_snapshot(app: str = 'inside-sales') -> BuilderSnapshot:
    return BuilderSnapshot(
        workflow_id=uuid.uuid4(),
        version_id=None,
        workflow_type='crm',
        app_id=app,
        definition=_voice_definition(),
        data_hash='hash-1',
        selected_node_id=None,
        view_mode='edit',
    )


def _make_ctx(*, builder: Any, auth: Any) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(builder_context=builder, auth=auth, scratch={}),
    )


def _resolver_response() -> ResolveUpstreamVariablesResponse:
    """One canonical outcome (answered) + one resumable event (voice.answered)."""
    return ResolveUpstreamVariablesResponse(
        fields=[
            UpstreamField(
                path=_OUTCOME_FIELD, type='enum', source='step',
                source_node_id=_VOICE_NODE_ID,
            ),
        ],
        sample={_OUTCOME_FIELD: None},
        unresolved=[],
        events=[
            UpstreamEvent(
                event_name='voice.answered', source_node_id=_VOICE_NODE_ID,
                provider='bolna',
            ),
        ],
        outcome_enums=[
            UpstreamOutcomeEnum(
                canonical='answered', provider_label='bolna_answered',
                source_node_id=_VOICE_NODE_ID, provider='bolna',
                field=_OUTCOME_FIELD,
            ),
        ],
    )


def _wrap(ops: list[dict[str, Any]], rationale: str = 'test') -> str:
    return json.dumps({'ops_json': json.dumps(ops), 'rationale': rationale})


def _conditional_add_op(value: str) -> dict[str, Any]:
    """Add a conditional that branches on the voice outcome field == value, then
    wire voice -> conditional so the resolver can see the producer upstream."""
    return {
        'op': 'add_node',
        'node_id': 'cond-1',
        'payload': {
            'node_type': 'logic.conditional',
            'config': {
                'branches': [
                    {
                        'id': 'b1',
                        'label': 'Matched',
                        'predicate': {
                            'field': _OUTCOME_FIELD,
                            'op': 'eq',
                            'value': value,
                        },
                    },
                ],
            },
        },
    }


def _wait_add_op(event_name: str) -> dict[str, Any]:
    return {
        'op': 'add_node',
        'node_id': 'wait-1',
        'payload': {
            'node_type': 'logic.wait',
            'config': {
                'mode': 'event',
                'event_name': event_name,
                'correlation': {'recipient_id_field': 'recipient_id'},
            },
        },
    }


def _connect_op(target: str) -> dict[str, Any]:
    return {
        'op': 'connect',
        'node_id': f'voice-to-{target}',
        'payload': {
            'source_node_id': _VOICE_NODE_ID,
            'output_id': 'success',
            'target_node_id': target,
            'edge_id': f'e-voice-{target}',
        },
    }


async def _call(ctx: SimpleNamespace, args: str) -> dict:
    app_id = ctx.context.builder_context.app_id
    with patch(
        'app.services.orchestration_authoring.orchestration_authoring_pack.'
        '_assert_builder_workflow_still_owned',
        new=AsyncMock(return_value=app_id),
    ), patch(
        'app.services.orchestration_authoring.orchestration_authoring_pack.'
        'resolve_upstream_variables',
        new=AsyncMock(return_value=_resolver_response()),
    ):
        return json.loads(await _apply_patch_handler(ctx, args))


class OutcomeEventReasonCodesRegisteredTests(unittest.TestCase):
    def test_unknown_outcome_in_reason_codes(self) -> None:
        self.assertIn('UNKNOWN_OUTCOME', REASON_CODES)

    def test_unknown_event_in_reason_codes(self) -> None:
        self.assertIn('UNKNOWN_EVENT', REASON_CODES)


class ConditionalValueGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_outcome_rejected(self) -> None:
        ctx = _make_ctx(builder=_make_snapshot(), auth=_make_auth())
        ops = [_conditional_add_op('definitely_not_a_real_outcome'), _connect_op('cond-1')]
        decoded = await _call(ctx, _wrap(ops))
        self.assertEqual(decoded['status'], 'error')
        self.assertEqual(decoded['meta']['reason_code'], 'UNKNOWN_OUTCOME')

    async def test_valid_canonical_outcome_passes(self) -> None:
        ctx = _make_ctx(builder=_make_snapshot(), auth=_make_auth())
        ops = [_conditional_add_op('answered'), _connect_op('cond-1')]
        decoded = await _call(ctx, _wrap(ops))
        self.assertEqual(decoded['status'], 'ok', decoded)


class WaitEventGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_event_rejected(self) -> None:
        ctx = _make_ctx(builder=_make_snapshot(), auth=_make_auth())
        ops = [_wait_add_op('voice.not_a_real_event'), _connect_op('wait-1')]
        decoded = await _call(ctx, _wrap(ops))
        self.assertEqual(decoded['status'], 'error')
        self.assertEqual(decoded['meta']['reason_code'], 'UNKNOWN_EVENT')

    async def test_valid_event_passes(self) -> None:
        ctx = _make_ctx(builder=_make_snapshot(), auth=_make_auth())
        ops = [_wait_add_op('voice.answered'), _connect_op('wait-1')]
        decoded = await _call(ctx, _wrap(ops))
        self.assertEqual(decoded['status'], 'ok', decoded)


if __name__ == '__main__':
    unittest.main()
