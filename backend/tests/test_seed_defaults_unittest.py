import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.seed_defaults import _seed_adversarial_contract_defaults


class SeedDefaultsTests(unittest.IsolatedAsyncioTestCase):
    async def test_seed_adversarial_contract_defaults_writes_system_shared_setting(self):
        session = AsyncMock()

        await _seed_adversarial_contract_defaults(session)

        session.execute.assert_awaited()
        session.flush.assert_awaited()
