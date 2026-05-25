import sys
import unittest
import uuid
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

fake_database = ModuleType('app.database')
fake_database.get_db = None
sys.modules.setdefault('app.database', fake_database)

from app.routes.admin import UpdateUserRequest, update_user


def _auth(*permissions: str):
    return SimpleNamespace(
        is_owner=False,
        permissions=frozenset(permissions),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )


class AdminUserPermissionSplitTests(unittest.IsolatedAsyncioTestCase):
    async def test_display_name_update_requires_user_manage_permission(self):
        db = AsyncMock()

        with self.assertRaises(HTTPException) as ctx:
            await update_user(
                user_id=uuid.uuid4(),
                body=UpdateUserRequest(displayName='Renamed User'),
                request=object(),
                auth=_auth(),
                db=db,
            )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, 'Missing permission: user:manage')
        db.scalar.assert_not_awaited()

    async def test_display_name_update_passes_gate_with_user_manage(self):
        db = AsyncMock()
        db.scalar.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            await update_user(
                user_id=uuid.uuid4(),
                body=UpdateUserRequest(displayName='Renamed User'),
                request=object(),
                auth=_auth('user:manage'),
                db=db,
            )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, 'User not found')
        db.scalar.assert_awaited_once()

    async def test_is_active_update_requires_user_manage_permission(self):
        db = AsyncMock()

        with self.assertRaises(HTTPException) as ctx:
            await update_user(
                user_id=uuid.uuid4(),
                body=UpdateUserRequest(isActive=False),
                request=object(),
                auth=_auth(),
                db=db,
            )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, 'Missing permission: user:manage')
        db.scalar.assert_not_awaited()

    async def test_role_assignment_update_requires_role_manage_permission(self):
        db = AsyncMock()

        with self.assertRaises(HTTPException) as ctx:
            await update_user(
                user_id=uuid.uuid4(),
                body=UpdateUserRequest(roleId=str(uuid.uuid4())),
                request=object(),
                auth=_auth('user:manage'),
                db=db,
            )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, 'Missing permission: role:manage')
        db.scalar.assert_not_awaited()

    async def test_role_assignment_update_does_not_require_user_manage_permission(self):
        db = AsyncMock()
        db.scalar.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            await update_user(
                user_id=uuid.uuid4(),
                body=UpdateUserRequest(roleId=str(uuid.uuid4())),
                request=object(),
                auth=_auth('role:manage'),
                db=db,
            )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, 'User not found')
        db.scalar.assert_awaited_once()

    async def test_empty_update_is_rejected_for_non_owner(self):
        db = AsyncMock()

        with self.assertRaises(HTTPException) as ctx:
            await update_user(
                user_id=uuid.uuid4(),
                body=UpdateUserRequest(),
                request=object(),
                auth=_auth('user:manage', 'role:manage'),
                db=db,
            )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, 'No permitted changes in request')
        db.scalar.assert_not_awaited()
