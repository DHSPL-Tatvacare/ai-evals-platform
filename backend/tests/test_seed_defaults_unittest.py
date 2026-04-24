import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.services.seed_defaults import _seed_adversarial_contract_defaults, seed_owner_role


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _AllResult:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)


class SeedDefaultsTests(unittest.IsolatedAsyncioTestCase):
    async def test_seed_adversarial_contract_defaults_writes_system_shared_setting(self):
        session = AsyncMock()

        await _seed_adversarial_contract_defaults(session)

        session.execute.assert_awaited()
        session.flush.assert_awaited()

    async def test_seed_owner_role_creates_system_owner_role_when_missing(self):
        """Phase 3: ``seed_owner_role`` creates the Owner role AND grants it
        every active app via ``role_app_access`` so ``AuthContext.app_access``
        stays the single source of truth (no Owner-only bypass in scope
        checks)."""
        session = AsyncMock()
        session.add = Mock()
        created_role_id = uuid.uuid4()

        async def _flush():
            last_added = session.add.call_args.args[0]
            if getattr(last_added, 'id', None) is None and hasattr(last_added, 'name'):
                last_added.id = created_role_id

        session.flush.side_effect = _flush
        session.execute.side_effect = [
            _ScalarOneOrNoneResult(None),
            # No active apps -> backfill exits early.
            _AllResult([]),
        ]

        role_id = await seed_owner_role(session, uuid.uuid4())

        added_role = session.add.call_args.args[0]
        self.assertEqual(role_id, created_role_id)
        self.assertEqual(added_role.name, 'Owner')
        self.assertEqual(added_role.description, 'Full access')
        self.assertTrue(added_role.is_system)
        session.flush.assert_awaited()

    async def test_seed_owner_role_reuses_existing_role_without_reseeding(self):
        """Existing Owner role is reused; backfill still runs but adds no
        rows when every active app already has a ``role_app_access`` grant."""
        existing_role = SimpleNamespace(id=uuid.uuid4(), name='Owner', is_system=True)
        session = AsyncMock()
        session.add = Mock()
        session.execute.side_effect = [
            _ScalarOneOrNoneResult(existing_role),
            # Backfill: no active apps registered, so no grants to add.
            _AllResult([]),
        ]

        role_id = await seed_owner_role(session, uuid.uuid4())

        self.assertEqual(role_id, existing_role.id)
        session.add.assert_not_called()
        session.flush.assert_not_awaited()
