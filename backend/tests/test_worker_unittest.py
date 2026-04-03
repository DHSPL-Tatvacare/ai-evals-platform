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
    async def test_run_worker_waits_for_schema_before_recovery(self):
        calls: list[str] = []

        async def fake_wait_for_schema():
            calls.append('wait')

        async def fake_recover_stale_jobs():
            calls.append('recover_jobs')

        async def fake_recover_stale_eval_runs():
            calls.append('recover_runs')

        async def fake_worker_loop():
            calls.append('worker_loop')

        async def fake_recovery_loop():
            calls.append('recovery_loop')

        with (
            patch.object(worker_entry, '_wait_for_worker_schema', side_effect=fake_wait_for_schema),
            patch.object(worker_entry, 'recover_stale_jobs', side_effect=fake_recover_stale_jobs),
            patch.object(worker_entry, 'recover_stale_eval_runs', side_effect=fake_recover_stale_eval_runs),
            patch.object(worker_entry, 'worker_loop', side_effect=fake_worker_loop),
            patch.object(worker_entry, 'recovery_loop', side_effect=fake_recovery_loop),
            patch.object(worker_entry.engine, 'dispose', new=AsyncMock()),
        ):
            await worker_entry.run_worker()

        self.assertEqual(
            calls,
            ['wait', 'recover_jobs', 'recover_runs', 'worker_loop', 'recovery_loop'],
        )


class WorkerSchemaWaitTests(unittest.IsolatedAsyncioTestCase):
    async def test_wait_for_worker_schema_retries_until_tables_exist(self):
        responses = iter([
            (False, False),
            (True, False),
            (True, True),
        ])

        class _FakeResult:
            def __init__(self, row):
                self._row = row

            def one(self):
                return self._row

        class _FakeConnection:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def execute(self, _stmt):
                return _FakeResult(next(responses))

        with (
            patch.object(worker_entry.engine, 'connect', return_value=_FakeConnection(), create=True),
            patch('app.worker.asyncio.sleep', new=AsyncMock()),
        ):
            await worker_entry._wait_for_worker_schema(timeout_seconds=3, poll_interval_seconds=0)
