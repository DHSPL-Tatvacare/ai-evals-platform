import asyncio
import os
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

fake_database = ModuleType('app.database')
fake_database.async_session = None
fake_database.engine = SimpleNamespace(dispose=AsyncMock())
sys.modules['app.database'] = fake_database

import app.worker as worker_entry  # noqa: E402


class WorkerStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_worker_bootstraps_schema_before_recovery(self):
        calls: list[str] = []

        async def fake_bootstrap_schema():
            calls.append('bootstrap')

        async def fake_recover_stale_jobs():
            calls.append('recover_jobs')

        async def fake_recover_stale_eval_runs():
            calls.append('recover_runs')

        async def fake_worker_loop():
            calls.append('worker_loop')

        async def fake_recovery_loop():
            calls.append('recovery_loop')

        with (
            patch.object(worker_entry, 'bootstrap_database_schema', side_effect=fake_bootstrap_schema),
            patch.object(worker_entry, 'recover_stale_jobs', side_effect=fake_recover_stale_jobs),
            patch.object(worker_entry, 'recover_stale_eval_runs', side_effect=fake_recover_stale_eval_runs),
            patch.object(worker_entry, 'worker_loop', side_effect=fake_worker_loop),
            patch.object(worker_entry, 'recovery_loop', side_effect=fake_recovery_loop),
            patch.object(worker_entry.engine, 'dispose', new=AsyncMock()),
        ):
            await worker_entry.run_worker()

        self.assertEqual(
            calls,
            ['bootstrap', 'recover_jobs', 'recover_runs', 'worker_loop', 'recovery_loop'],
        )
