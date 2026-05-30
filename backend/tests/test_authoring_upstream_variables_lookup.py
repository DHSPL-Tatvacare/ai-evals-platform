"""A-Step 1 — `list_upstream_variables` exposes the producer vocabulary.

The authoring agent needs the SAME upstream {fields, events, outcome_enums,
unresolved} the builder's input pane gets, so it can wire a downstream
conditional / wait without inventing outcome or event magic-strings. This tool
WRAPS `resolve_upstream_variables` against the CURRENT builder definition — it
never re-derives vocabulary. These tests assert the wrap contract: the handler
parses the builder definition into node/edge models, forwards the target node,
and surfaces the resolver's event names + outcome enums verbatim. No live
external API, no live DB.
"""
from __future__ import annotations

import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas.orchestration import (
    ResolveUpstreamVariablesResponse,
    UpstreamEvent,
    UpstreamField,
    UpstreamOutcomeEnum,
    UpstreamUnresolved,
)
from app.services.orchestration_authoring.orchestration_authoring_pack import (
    OrchestrationAuthoringPack,
    _list_upstream_variables_handler,
)


def _make_auth(app: str = 'inside-sales') -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        permissions=frozenset({'orchestration:manage'}),
        app_access=frozenset({app}),
        is_owner=False,
    )


_VOICE_NODE_ID = 'voice-1'
_WAIT_NODE_ID = 'wait-1'


def _voice_then_wait_definition() -> dict:
    """A voice producer feeding a downstream wait — the canonical case the
    agent resolves to learn which provider outcomes/events it may branch on."""
    return {
        'nodes': [
            {
                'id': _VOICE_NODE_ID,
                'type': 'voice.place_call',
                'config': {'connection_id': str(uuid.uuid4())},
                'data': {'label': 'Place call'},
            },
            {
                'id': _WAIT_NODE_ID,
                'type': 'logic.wait',
                'config': {},
                'data': {'label': 'Wait for outcome'},
            },
        ],
        'edges': [
            {'id': 'e1', 'source': _VOICE_NODE_ID, 'target': _WAIT_NODE_ID},
        ],
    }


def _make_snapshot(app: str = 'inside-sales') -> SimpleNamespace:
    return SimpleNamespace(
        workflow_id=uuid.uuid4(),
        version_id=None,
        workflow_type='crm',
        app_id=app,
        definition=_voice_then_wait_definition(),
        data_hash='hash-1',
        selected_node_id=None,
        view_mode='edit',
    )


def _make_ctx(*, builder=None, auth=None, scratch=None) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(
            builder_context=builder,
            auth=auth,
            scratch=scratch if scratch is not None else {},
        ),
    )


def _fake_resolver_response() -> ResolveUpstreamVariablesResponse:
    """What the real resolver would return for the fixtured voice node — a
    provider-specific outcome enum + resumable event the agent must reuse."""
    field = f'steps.{_VOICE_NODE_ID}.outcome'
    return ResolveUpstreamVariablesResponse(
        fields=[
            UpstreamField(
                path=field, type='enum', source='step',
                source_node_id=_VOICE_NODE_ID,
            ),
        ],
        sample={field: None},
        unresolved=[
            UpstreamUnresolved(
                node_id='other', label='Event trigger',
                reason='Event payload fields are not known until the workflow runs.',
            ),
        ],
        events=[
            UpstreamEvent(
                event_name='voice.answered', source_node_id=_VOICE_NODE_ID,
                provider='bolna',
            ),
        ],
        outcome_enums=[
            UpstreamOutcomeEnum(
                canonical='answered', provider_label='bolna_answered',
                source_node_id=_VOICE_NODE_ID, provider='bolna', field=field,
            ),
        ],
    )


class UpstreamVariablesToolSurfaceTests(unittest.TestCase):
    def test_pack_exposes_list_upstream_variables(self) -> None:
        names = {s['name'] for s in OrchestrationAuthoringPack().tool_specs()}
        self.assertIn('list_upstream_variables', names)

    def test_handler_registered(self) -> None:
        handlers = OrchestrationAuthoringPack().tool_handlers()
        self.assertIn('list_upstream_variables', handlers)

    def test_schema_is_strict_object_requiring_target_node_id(self) -> None:
        spec = next(
            s for s in OrchestrationAuthoringPack().tool_specs()
            if s['name'] == 'list_upstream_variables'
        )
        schema = spec['params_json_schema']
        self.assertEqual(schema['type'], 'object')
        self.assertFalse(schema['additionalProperties'])
        self.assertIn('target_node_id', schema['properties'])
        self.assertIn('target_node_id', schema.get('required', []))


class UpstreamVariablesWrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_resolver_events_and_outcome_enums(self) -> None:
        ctx = _make_ctx(builder=_make_snapshot(), auth=_make_auth())
        args = json.dumps({'target_node_id': _WAIT_NODE_ID})
        with patch(
            'app.services.orchestration_authoring.orchestration_authoring_pack.'
            '_assert_builder_workflow_still_owned',
            new=AsyncMock(return_value='inside-sales'),
        ), patch(
            'app.services.orchestration_authoring.orchestration_authoring_pack.'
            'resolve_upstream_variables',
            new=AsyncMock(return_value=_fake_resolver_response()),
        ):
            result = await _list_upstream_variables_handler(ctx, args)

        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'ok')
        payload = decoded['payload']
        event_names = {e['eventName'] for e in payload['events']}
        self.assertEqual(event_names, {'voice.answered'})
        canonicals = {o['canonical'] for o in payload['outcomeEnums']}
        self.assertEqual(canonicals, {'answered'})
        labels = {o['providerLabel'] for o in payload['outcomeEnums']}
        self.assertEqual(labels, {'bolna_answered'})
        # fields + unresolved travel through unchanged
        self.assertEqual(len(payload['fields']), 1)
        self.assertEqual(len(payload['unresolved']), 1)
        self.assertNotEqual(
            decoded.get('meta', {}).get('reason_code'),
            'CREDENTIAL_LEAK_BLOCKED',
        )

    async def test_forwards_builder_definition_and_target_to_resolver(self) -> None:
        ctx = _make_ctx(builder=_make_snapshot(), auth=_make_auth())
        args = json.dumps({'target_node_id': _WAIT_NODE_ID})
        resolver = AsyncMock(return_value=_fake_resolver_response())
        with patch(
            'app.services.orchestration_authoring.orchestration_authoring_pack.'
            '_assert_builder_workflow_still_owned',
            new=AsyncMock(return_value='inside-sales'),
        ), patch(
            'app.services.orchestration_authoring.orchestration_authoring_pack.'
            'resolve_upstream_variables',
            new=resolver,
        ):
            await _list_upstream_variables_handler(ctx, args)

        self.assertEqual(resolver.await_count, 1)
        kwargs = resolver.await_args.kwargs
        self.assertEqual(kwargs['target_node_id'], _WAIT_NODE_ID)
        self.assertEqual(kwargs['app_id'], 'inside-sales')
        self.assertEqual(kwargs['workflow_type'], 'crm')
        # builder definition nodes/edges parsed into the resolver's models
        node_ids = {n.id for n in kwargs['nodes']}
        self.assertEqual(node_ids, {_VOICE_NODE_ID, _WAIT_NODE_ID})
        self.assertEqual(len(kwargs['edges']), 1)
        self.assertEqual(kwargs['edges'][0].source, _VOICE_NODE_ID)

    async def test_missing_target_node_id_is_node_config_invalid(self) -> None:
        ctx = _make_ctx(builder=_make_snapshot(), auth=_make_auth())
        with patch(
            'app.services.orchestration_authoring.orchestration_authoring_pack.'
            '_assert_builder_workflow_still_owned',
            new=AsyncMock(return_value='inside-sales'),
        ):
            result = await _list_upstream_variables_handler(ctx, '{}')
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'error')
        self.assertEqual(
            decoded.get('meta', {}).get('reason_code'), 'NODE_CONFIG_INVALID',
        )


if __name__ == '__main__':
    unittest.main()
