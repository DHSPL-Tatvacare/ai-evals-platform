"""Phase 1 Step 3 — lookup tools are tenant + app scoped, credential-stripped.

Two acceptance items: every lookup query has tenant_id AND app_id in the
WHERE clause; serialized output never carries fields named in the
credential blocklist.
"""
from __future__ import annotations

import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.orchestration_authoring.lookup_models import (
    CREDENTIAL_FIELD_BLOCKLIST,
    contains_credential_fields,
)
from app.services.orchestration_authoring.orchestration_authoring_pack import (
    OrchestrationAuthoringPack,
    _list_node_types_handler,
)


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


def _make_ctx(*, builder=None, auth=None, scratch=None) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(
            builder_context=builder,
            auth=auth,
            scratch=scratch if scratch is not None else {},
        ),
    )


class CredentialBlocklistTests(unittest.TestCase):
    def test_blocklist_covers_known_credential_field_names(self) -> None:
        for name in (
            'api_key', 'config_encrypted', 'webhook_token', 'access_token',
            'password', 'secret', 'bolna_api_key', 'wati_api_key',
        ):
            self.assertIn(name, CREDENTIAL_FIELD_BLOCKLIST)

    def test_recursive_walker_finds_nested_field(self) -> None:
        payload = {'items': [{'id': 'x', 'config': {'api_key': 'leak'}}]}
        self.assertEqual(contains_credential_fields(payload), 'api_key')

    def test_recursive_walker_passes_clean_payload(self) -> None:
        payload = {'items': [{'id': 'x', 'name': 'y'}]}
        self.assertIsNone(contains_credential_fields(payload))


class LookupSqlScopingTests(unittest.IsolatedAsyncioTestCase):
    """Static guarantee: every lookup query embeds tenant_id AND app_id.

    These tests inspect the SQL produced by the SQLAlchemy `select(...)`
    statements built by each handler. We cannot run the handler against a
    live DB in unit tests — we patch `async_session` and capture the
    statement(s) it executes.
    """

    async def test_list_provider_connections_filters_by_tenant_and_app(self) -> None:
        from app.services.orchestration_authoring import (
            orchestration_authoring_pack as pack_mod,
        )

        captured: dict = {}

        class _FakeResult:
            def scalars(self):
                return self
            def all(self):
                return []

        class _FakeSession:
            async def __aenter__(self_inner):
                return self_inner
            async def __aexit__(self_inner, exc_type, exc, tb):
                return None
            async def execute(self_inner, stmt):
                captured['stmt'] = str(stmt)
                return _FakeResult()

        def _fake_session_factory():
            return _FakeSession()

        original = pack_mod
        # Patch the `async_session` import the handler uses lazily.
        import app.database as db_mod
        orig = db_mod.async_session
        db_mod.async_session = _fake_session_factory  # type: ignore[assignment]
        try:
            ctx = _make_ctx(builder=_make_snapshot(), auth=_make_auth())
            args = json.dumps({'provider': 'wati'})
            with patch.object(
                pack_mod,
                '_assert_builder_workflow_still_owned',
                new=AsyncMock(return_value='inside-sales'),
            ):
                await pack_mod._list_provider_connections_handler(ctx, args)
        finally:
            db_mod.async_session = orig  # type: ignore[assignment]
        del original
        sql = captured['stmt'].lower()
        self.assertIn('tenant_id', sql)
        self.assertIn('app_id', sql)
        self.assertIn('provider', sql)

    async def test_list_action_templates_query_filters(self) -> None:
        from app.services.orchestration_authoring import (
            orchestration_authoring_pack as pack_mod,
        )

        captured: dict = {}

        class _FakeResult:
            def scalars(self):
                return self
            def all(self):
                return []

        class _FakeSession:
            async def __aenter__(self_inner):
                return self_inner
            async def __aexit__(self_inner, exc_type, exc, tb):
                return None
            async def execute(self_inner, stmt):
                captured['stmt'] = str(stmt)
                return _FakeResult()

        import app.database as db_mod
        orig = db_mod.async_session
        db_mod.async_session = lambda: _FakeSession()  # type: ignore[assignment]
        try:
            ctx = _make_ctx(builder=_make_snapshot(), auth=_make_auth())
            args = json.dumps({'channel': 'whatsapp'})
            with patch.object(
                pack_mod,
                '_assert_builder_workflow_still_owned',
                new=AsyncMock(return_value='inside-sales'),
            ):
                await pack_mod._list_action_templates_handler(ctx, args)
        finally:
            db_mod.async_session = orig  # type: ignore[assignment]
        sql = captured['stmt'].lower()
        self.assertIn('tenant_id', sql)
        self.assertIn('app_id', sql)
        self.assertIn('channel', sql)


class LookupResponseShapeTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_node_types_works_without_db(self) -> None:
        ctx = _make_ctx(builder=_make_snapshot(), auth=_make_auth())
        with patch(
            'app.services.orchestration_authoring.orchestration_authoring_pack.'
            '_assert_builder_workflow_still_owned',
            new=AsyncMock(return_value='inside-sales'),
        ):
            result = await _list_node_types_handler(ctx, '{}')
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'ok')
        self.assertGreater(len(decoded['payload']['items']), 0)
        # Every entry should expose node_type / category / workflow_types
        for item in decoded['payload']['items']:
            self.assertIn('node_type', item)
            self.assertIn('category', item)
            self.assertIn('workflow_types', item)
        # Egress filter should not have tripped
        self.assertNotEqual(decoded.get('meta', {}).get('reason_code'), 'CREDENTIAL_LEAK_BLOCKED')


class PackToolSurfaceTests(unittest.TestCase):
    def test_pack_exposes_six_tools(self) -> None:
        names = [s['name'] for s in OrchestrationAuthoringPack().tool_specs()]
        self.assertEqual(set(names), {
            'apply_patch',
            'list_node_types',
            'list_provider_connections',
            'list_action_templates',
            'list_wati_templates',
            'list_cohort_datasets',
        })

    def test_every_tool_schema_uses_strict_object(self) -> None:
        for spec in OrchestrationAuthoringPack().tool_specs():
            schema = spec['params_json_schema']
            self.assertEqual(schema['type'], 'object')
            self.assertFalse(schema['additionalProperties'])


class CredentialFieldRegressionTests(unittest.TestCase):
    """Regression: any *_pack response model must not declare a credential field."""

    def test_response_models_have_no_blocklisted_fields(self) -> None:
        from app.services.orchestration_authoring.lookup_models import (
            ActionTemplateRef, ActionTemplatesList, CohortDatasetRef,
            CohortDatasetsList, NodeTypeRef, NodeTypesList,
            ProviderConnectionRef, ProviderConnectionsList,
            WatiTemplateRef, WatiTemplatesList,
        )
        for cls in (
            ActionTemplateRef, ActionTemplatesList, CohortDatasetRef,
            CohortDatasetsList, NodeTypeRef, NodeTypesList,
            ProviderConnectionRef, ProviderConnectionsList,
            WatiTemplateRef, WatiTemplatesList,
        ):
            field_names = set(cls.model_fields.keys())
            offenders = field_names & CREDENTIAL_FIELD_BLOCKLIST
            self.assertFalse(
                offenders,
                f'{cls.__name__} declares forbidden field(s): {offenders}',
            )


if __name__ == '__main__':
    unittest.main()
