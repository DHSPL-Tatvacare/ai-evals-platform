import os
import sys
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.seed_defaults import _seed_adversarial_contract_defaults, seed_owner_role


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class SeedDefaultsTests(unittest.IsolatedAsyncioTestCase):
    async def test_seed_adversarial_contract_defaults_writes_system_shared_setting(self):
        session = AsyncMock()

        await _seed_adversarial_contract_defaults(session)

        session.execute.assert_awaited()
        session.flush.assert_awaited()

    async def test_seed_owner_role_creates_system_owner_role_when_missing(self):
        session = AsyncMock()
        session.add = Mock()
        session.execute.return_value = _ScalarOneOrNoneResult(None)
        created_role_id = uuid.uuid4()

        async def _flush():
            session.add.call_args.args[0].id = created_role_id

        session.flush.side_effect = _flush

        role_id = await seed_owner_role(session, uuid.uuid4())

        added_role = session.add.call_args.args[0]
        self.assertEqual(role_id, created_role_id)
        self.assertEqual(added_role.name, 'Owner')
        self.assertEqual(added_role.description, 'Full access')
        self.assertTrue(added_role.is_system)
        session.flush.assert_awaited()

    async def test_seed_owner_role_reuses_existing_role_without_reseeding(self):
        existing_role = SimpleNamespace(id=uuid.uuid4())
        session = AsyncMock()
        session.add = Mock()
        session.execute.return_value = _ScalarOneOrNoneResult(existing_role)

        role_id = await seed_owner_role(session, uuid.uuid4())

        self.assertEqual(role_id, existing_role.id)
        session.add.assert_not_called()
        session.flush.assert_not_awaited()
