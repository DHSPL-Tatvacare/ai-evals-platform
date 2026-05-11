"""Phase 1 Step 8 — chat_stream_v2 builder-context gate.

Acceptance items:
- 404 on cross-tenant workflow_id (never leak existence)
- 403 on cross-app app_id
- Drops context (with audit log line) when 'orchestration:manage' is missing
"""
from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.auth.context import AuthContext
from app.services.report_builder.schemas import BuilderChatRequest


def _make_auth(*, tenant: uuid.UUID | None = None,
               with_perm: bool = True,
               apps: set[str] | None = None) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant or uuid.uuid4(),
        email='t@t',
        role_id=uuid.uuid4(),
        is_owner=False,
        permissions=frozenset({'orchestration:manage'} if with_perm else set()),
        app_access=frozenset(apps or {'inside-sales'}),
    )


def _body(*, app_id: str = 'inside-sales',
          page_app_id: str | None = 'inside-sales',
          workflow_id: str | None = None,
          definition: dict | None = None,
          data_hash: str = 'h1',
          view_mode: str = 'edit') -> BuilderChatRequest:
    payload: dict = {
        'app_id': app_id,
        'turn_id': str(uuid.uuid4()),
        'message': 'hi',
        'model': 'gpt-5',
    }
    if page_app_id is not None:
        payload['page_context'] = {
            'kind': 'orchestration_builder',
            'workflow_id': workflow_id or str(uuid.uuid4()),
            'workflow_type': 'crm',
            'app_id': page_app_id,
            'definition': definition or {'nodes': [], 'edges': []},
            'data_hash': data_hash,
            'view_mode': view_mode,
        }
    return BuilderChatRequest.model_validate(payload)


class PageContextSchemaTests(unittest.TestCase):
    def test_missing_pagecontext_is_ok(self) -> None:
        b = _body(page_app_id=None)
        self.assertIsNone(b.page_context)

    def test_kind_none_form_is_accepted(self) -> None:
        b = BuilderChatRequest.model_validate({
            'app_id': 'inside-sales',
            'turn_id': str(uuid.uuid4()),
            'message': 'hi',
            'model': 'gpt-5',
            'page_context': {'kind': 'none'},
        })
        self.assertIsNotNone(b.page_context)
        self.assertEqual(b.page_context.kind, 'none')

    def test_orchestration_builder_kind_is_validated(self) -> None:
        b = _body()
        self.assertIsNotNone(b.page_context)
        self.assertEqual(b.page_context.kind, 'orchestration_builder')

    def test_unknown_kind_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            BuilderChatRequest.model_validate({
                'app_id': 'inside-sales',
                'turn_id': str(uuid.uuid4()),
                'message': 'hi',
                'model': 'gpt-5',
                'page_context': {'kind': 'unknown_kind'},
            })


class ResolveBuilderSnapshotTests(unittest.IsolatedAsyncioTestCase):
    """Direct unit tests of `_resolve_builder_snapshot` (the route gate)."""

    async def test_no_pagecontext_returns_none(self) -> None:
        from app.routes.report_builder import _resolve_builder_snapshot
        snap = await _resolve_builder_snapshot(
            body=_body(page_app_id=None),
            auth=_make_auth(),
            db=MagicMock(),
        )
        self.assertIsNone(snap)

    async def test_drops_context_when_permission_missing(self) -> None:
        from app.routes.report_builder import _resolve_builder_snapshot
        fake_workflow = SimpleNamespace(
            id=uuid.uuid4(), app_id='inside-sales',
            current_published_version_id=None,
        )
        with patch('app.routes.report_builder.ensure_registered_app_access',
                   new=AsyncMock(return_value='inside-sales')), \
             patch('app.routes.report_builder.assert_workflow_owned',
                   new=AsyncMock(return_value=fake_workflow)):
            snap = await _resolve_builder_snapshot(
                body=_body(),
                auth=_make_auth(with_perm=False),
                db=MagicMock(),
            )
        self.assertIsNone(snap)

    async def test_app_mismatch_raises_400(self) -> None:
        from app.routes.report_builder import _resolve_builder_snapshot
        with patch('app.routes.report_builder.ensure_registered_app_access',
                   new=AsyncMock(return_value='whatever')):
            with self.assertRaises(HTTPException) as exc_ctx:
                await _resolve_builder_snapshot(
                    body=_body(app_id='inside-sales', page_app_id='voice-rx'),
                    auth=_make_auth(apps={'inside-sales', 'voice-rx'}),
                    db=MagicMock(),
                )
        self.assertEqual(exc_ctx.exception.status_code, 400)

    async def test_cross_app_no_access_returns_403(self) -> None:
        """User holds no access to the requested app — ensure_registered_app_access
        raises 403, the route gate propagates it."""
        from app.routes.report_builder import _resolve_builder_snapshot

        async def _fake_ensure(db, auth, app_slug, **kwargs):
            del db
            if app_slug not in auth.app_access:
                raise HTTPException(403, f'No access to app: {app_slug}')
            return app_slug

        with patch('app.routes.report_builder.ensure_registered_app_access',
                   side_effect=_fake_ensure):
            with self.assertRaises(HTTPException) as exc_ctx:
                # body.app_id matches pageContext.app_id, but neither is in
                # auth.app_access — the helper raises 403.
                await _resolve_builder_snapshot(
                    body=_body(app_id='voice-rx', page_app_id='voice-rx'),
                    auth=_make_auth(apps={'inside-sales'}),
                    db=MagicMock(),
                )
        self.assertEqual(exc_ctx.exception.status_code, 403)

    async def test_cross_tenant_workflow_returns_404(self) -> None:
        from app.routes import report_builder as route_mod

        async def _fake_assert(db, *, workflow_id, auth):
            del db, workflow_id, auth
            raise HTTPException(404, 'workflow not found')

        with patch.object(route_mod, 'ensure_registered_app_access',
                          new=AsyncMock(return_value='inside-sales')), \
             patch.object(route_mod, 'assert_workflow_owned',
                          side_effect=_fake_assert):
            with self.assertRaises(HTTPException) as exc_ctx:
                await route_mod._resolve_builder_snapshot(
                    body=_body(),
                    auth=_make_auth(),
                    db=MagicMock(),
                )
        self.assertEqual(exc_ctx.exception.status_code, 404)

    async def test_happy_path_returns_snapshot(self) -> None:
        from app.routes import report_builder as route_mod

        wf_id = uuid.uuid4()
        fake_workflow = SimpleNamespace(
            id=wf_id, app_id='inside-sales',
            current_published_version_id=None,
        )

        async def _fake_assert(db, *, workflow_id, auth):
            del db, workflow_id, auth
            return fake_workflow

        with patch.object(route_mod, 'ensure_registered_app_access',
                          new=AsyncMock(return_value='inside-sales')), \
              patch.object(route_mod, 'assert_workflow_owned',
                           side_effect=_fake_assert):
            snap = await route_mod._resolve_builder_snapshot(
                body=_body(workflow_id=str(wf_id)),
                auth=_make_auth(),
                db=MagicMock(),
            )
        self.assertIsNotNone(snap)
        self.assertEqual(str(snap.workflow_id), str(wf_id))
        self.assertEqual(snap.app_id, 'inside-sales')

    async def test_view_mode_drops_context(self) -> None:
        from app.routes import report_builder as route_mod

        fake_workflow = SimpleNamespace(
            id=uuid.uuid4(), app_id='inside-sales',
            current_published_version_id=None,
        )
        with patch.object(route_mod, 'ensure_registered_app_access',
                          new=AsyncMock(return_value='inside-sales')), \
             patch.object(route_mod, 'assert_workflow_owned',
                          new=AsyncMock(return_value=fake_workflow)):
            snap = await route_mod._resolve_builder_snapshot(
                body=_body(view_mode='view'),
                auth=_make_auth(),
                db=MagicMock(),
            )
        self.assertIsNone(snap)


if __name__ == '__main__':
    unittest.main()
