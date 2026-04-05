import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

fake_database = ModuleType('app.database')
fake_database.get_db = None
sys.modules.setdefault('app.database', fake_database)

import app.auth.app_scope as app_scope


class AppScopeTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_ensure_registered_app_access_allows_owner_without_explicit_app_grant(self):
        auth = SimpleNamespace(is_owner=True, app_access=frozenset())
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
