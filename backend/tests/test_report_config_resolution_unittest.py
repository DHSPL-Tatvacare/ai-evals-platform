import os
import sys
import unittest
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.mixins.shareable import Visibility
from app.services.reports.report_config_resolver import resolve_report_config


class _FakeSession:
    def __init__(self, scalar_results):
        self._scalar_results = list(scalar_results)
        self.scalar_calls = 0

    async def scalar(self, _stmt):
        self.scalar_calls += 1
        if not self._scalar_results:
            return None
        return self._scalar_results.pop(0)


def _report_config(**overrides):
    defaults = {
        'id': uuid.uuid4(),
        'app_id': 'kaira-bot',
        'report_id': 'default-single-run',
        'scope': 'single_run',
        'name': 'Default Single Run Report',
        'status': 'active',
        'is_default': True,
        'visibility': Visibility.SHARED,
        'presentation_config': {
            'sections': [
                {
                    'sectionId': 'kaira-summary',
                    'componentId': 'summary_cards',
                    'variant': 'kaira_overview',
                    'printable': True,
                },
            ],
        },
        'narrative_config': {
            'enabled': True,
            'assetKeys': {'systemPromptKey': 'system-a'},
        },
        'export_config': {'enabled': True, 'format': 'pdf', 'documentVariant': 'kaira-run-v1'},
        'default_report_run_visibility': Visibility.PRIVATE,
        'version': 3,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class ReportConfigResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_report_config_prefers_explicit_report_id(self):
        explicit = _report_config(report_id='quality-review')
        db = _FakeSession([explicit])

        result = await resolve_report_config(
            db,
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            app_id='kaira-bot',
            scope='single_run',
            report_id='quality-review',
        )

        self.assertIs(result, explicit)
        self.assertEqual(db.scalar_calls, 1)

    async def test_resolve_report_config_falls_back_to_default_for_scope(self):
        default = _report_config(report_id='default-cross-run', scope='cross_run')
        db = _FakeSession([None, default])

        result = await resolve_report_config(
            db,
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            app_id='kaira-bot',
            scope='cross_run',
            report_id=None,
        )

        self.assertIs(result, default)
        self.assertEqual(db.scalar_calls, 2)

