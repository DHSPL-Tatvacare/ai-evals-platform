import os
import sys
import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.mixins.shareable import Visibility
from app.models.report_artifact import ReportArtifact
from app.models.report_run import ReportRun
from app.services.reports.report_run_store import (
    ensure_report_run,
    fetch_single_run_artifact,
    persist_report_artifact,
)


class _FakeSession:
    def __init__(self, scalar_results):
        self._scalar_results = list(scalar_results)
        self.added = []
        self.flushes = 0

    async def scalar(self, _stmt):
        if not self._scalar_results:
            return None
        return self._scalar_results.pop(0)

    def add(self, model):
        self.added.append(model)

    async def flush(self):
        self.flushes += 1


def _report_config(**overrides):
    defaults = {
        'id': uuid.uuid4(),
        'app_id': 'inside-sales',
        'report_id': 'default-single-run',
        'scope': 'single_run',
        'version': 4,
        'default_report_run_visibility': Visibility.PRIVATE,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class ReportRunStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_report_run_creates_row_with_report_config_defaults(self):
        report_config = _report_config()
        job_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        source_eval_run_id = uuid.uuid4()
        db = _FakeSession([None])

        report_run = await ensure_report_run(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            job_id=job_id,
            report_config=report_config,
            source_eval_run_id=source_eval_run_id,
            visibility=None,
            llm_provider='openai',
            llm_model='gpt-5.4',
        )

        self.assertIsInstance(report_run, ReportRun)
        self.assertEqual(report_run.tenant_id, tenant_id)
        self.assertEqual(report_run.user_id, user_id)
        self.assertEqual(report_run.job_id, job_id)
        self.assertEqual(report_run.report_id, report_config.report_id)
        self.assertEqual(report_run.visibility, Visibility.PRIVATE)
        self.assertEqual(report_run.report_config_version, 4)
        self.assertEqual(report_run.llm_provider, 'openai')
        self.assertEqual(report_run.llm_model, 'gpt-5.4')
        self.assertEqual(db.flushes, 1)
        self.assertEqual(len(db.added), 1)

    async def test_persist_report_artifact_upserts_composed_output(self):
        report_run = ReportRun(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            app_id='inside-sales',
            report_id='default-single-run',
            scope='single_run',
            visibility=Visibility.SHARED,
        )
        report_run.id = uuid.uuid4()
        existing = ReportArtifact(
            report_run_id=report_run.id,
            tenant_id=report_run.tenant_id,
            app_id=report_run.app_id,
            report_id=report_run.report_id,
            scope=report_run.scope,
            artifact_data={'old': True},
        )
        db = _FakeSession([existing])

        artifact = await persist_report_artifact(
            db,
            report_run=report_run,
            artifact_data={'schemaVersion': 'v1', 'metadata': {'runId': 'run-1'}},
            source_run_count=1,
            latest_source_run_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
        )

        self.assertIs(artifact, existing)
        self.assertEqual(artifact.artifact_data['schemaVersion'], 'v1')
        self.assertEqual(artifact.source_run_count, 1)
        self.assertFalse(hasattr(artifact, 'visibility'))
        self.assertEqual(len(db.added), 0)

    async def test_fetch_single_run_artifact_returns_latest_completed_artifact(self):
        expected = {'schemaVersion': 'v1', 'metadata': {'runId': 'run-123'}}
        db = _FakeSession([expected])

        artifact = await fetch_single_run_artifact(
            db,
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            app_id='inside-sales',
            report_id='default-single-run',
        )

        self.assertEqual(artifact, expected)

