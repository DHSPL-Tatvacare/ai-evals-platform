import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

fake_database = ModuleType('app.database')
fake_database.get_db = None
sys.modules.setdefault('app.database', fake_database)

import app.auth.app_scope as app_scope


class AppScopeTests(unittest.IsolatedAsyncioTestCase):
    async def _make_request(
        self,
        *,
        method: str = 'GET',
        query_string: str = '',
        path_params: dict[str, str] | None = None,
        json_body: bytes | None = None,
        content_type: bytes = b'application/json',
    ) -> Request:
        payload = json_body or b''
        scope = {
            'type': 'http',
            'method': method,
            'path': '/',
            'query_string': query_string.encode(),
            'headers': [(b'content-type', content_type)],
            'path_params': path_params or {},
        }

        async def receive():
            return {'type': 'http.request', 'body': payload, 'more_body': False}

        return Request(scope, receive)

    def test_candidate_param_names_returns_snake_and_camel_variants(self):
        self.assertEqual(
            app_scope.candidate_param_names('app_id'),
            ('app_id', 'appId'),
        )
        self.assertEqual(
            app_scope.candidate_param_names('appId'),
            ('appId', 'app_id'),
        )

    async def test_validate_registered_app_slug_returns_normalized_registered_slug(self):
        with patch.object(
            app_scope,
            'load_active_app_map',
            AsyncMock(return_value={'voice-rx': object()}),
        ):
            resolved = await app_scope.validate_registered_app_slug(
                db=AsyncMock(),
                app_slug=' voice-rx ',
            )

        self.assertEqual(resolved, 'voice-rx')

    async def test_validate_registered_app_slug_rejects_unknown_slug(self):
        with patch.object(
            app_scope,
            'load_active_app_map',
            AsyncMock(return_value={'voice-rx': object()}),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await app_scope.validate_registered_app_slug(
                    db=AsyncMock(),
                    app_slug='unknown-app',
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, 'App not found')

    async def test_ensure_registered_app_access_allows_owner_with_grant_in_app_access(self):
        """Phase 3: Owner access is represented truthfully in ``auth.app_access``
        at auth-load time, so ``ensure_registered_app_access`` simply reads that
        single source of truth. No Owner-only bypass remains in this helper."""
        auth = SimpleNamespace(is_owner=True, app_access=frozenset({'kaira-bot'}))
        with patch.object(
            app_scope,
            'load_active_app_map',
            AsyncMock(return_value={'kaira-bot': object()}),
        ):
            resolved = await app_scope.ensure_registered_app_access(
                db=AsyncMock(),
                auth=auth,
                app_slug='kaira-bot',
            )

        self.assertEqual(resolved, 'kaira-bot')

    async def test_ensure_registered_app_access_denies_owner_with_empty_app_access(self):
        """Phase 3 regression: the helper no longer short-circuits on
        ``is_owner``. If ``auth.app_access`` is empty (e.g. because the seed or
        auth-loader failed to expand Owner grants) the caller must be denied so
        the failure surfaces rather than silently permitting an Owner with no
        resolvable app."""
        auth = SimpleNamespace(is_owner=True, app_access=frozenset())
        with patch.object(
            app_scope,
            'load_active_app_map',
            AsyncMock(return_value={'kaira-bot': object()}),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await app_scope.ensure_registered_app_access(
                    db=AsyncMock(),
                    auth=auth,
                    app_slug='kaira-bot',
                )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, 'No access to app: kaira-bot')

    async def test_ensure_registered_app_access_rejects_registered_app_without_grant(self):
        auth = SimpleNamespace(is_owner=False, app_access=frozenset({'voice-rx'}))
        with patch.object(
            app_scope,
            'load_active_app_map',
            AsyncMock(return_value={'voice-rx': object(), 'inside-sales': object()}),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await app_scope.ensure_registered_app_access(
                    db=AsyncMock(),
                    auth=auth,
                    app_slug='inside-sales',
                )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, 'No access to app: inside-sales')

    async def test_validate_registered_app_slug_allows_missing_value_when_not_required(self):
        resolved = await app_scope.validate_registered_app_slug(
            db=AsyncMock(),
            app_slug='   ',
            required=False,
        )

        self.assertIsNone(resolved)

    async def test_extract_app_slug_from_request_prefers_query_alias(self):
        request = await self._make_request(query_string='appId=kaira-bot')

        resolved = await app_scope.extract_app_slug_from_request(request, 'app_id')

        self.assertEqual(resolved, 'kaira-bot')

    async def test_extract_app_slug_from_request_reads_path_alias(self):
        request = await self._make_request(path_params={'appId': 'inside-sales'})

        resolved = await app_scope.extract_app_slug_from_request(request, 'app_id')

        self.assertEqual(resolved, 'inside-sales')

    async def test_extract_app_slug_from_request_reads_body_alias(self):
        request = await self._make_request(
            method='POST',
            json_body=b'{"appId":"voice-rx"}',
        )

        resolved = await app_scope.extract_app_slug_from_request(request, 'app_id')

        self.assertEqual(resolved, 'voice-rx')
