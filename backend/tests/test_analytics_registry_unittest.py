"""unittest coverage for analytics registry wiring."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

REGISTRY_IMPORT_ERROR = None

try:
    from app.services.reports.registry import get_analytics_app_config
except Exception as exc:  # pragma: no cover - environment-dependent optional deps
    REGISTRY_IMPORT_ERROR = exc
    get_analytics_app_config = None


@unittest.skipIf(
    REGISTRY_IMPORT_ERROR is not None,
    f'analytics registry imports optional backend deps not installed in this environment: {REGISTRY_IMPORT_ERROR}',
)
class AnalyticsRegistryTests(unittest.TestCase):
    def test_kaira_config_exposes_all_expected_capabilities(self):
        config = get_analytics_app_config('kaira-bot')
        self.assertIsNotNone(config)
        assert config is not None
        self.assertTrue(config.capabilities.single_run_report)
        self.assertTrue(config.capabilities.cross_run_analytics)
        self.assertTrue(config.capabilities.pdf_export)
        self.assertTrue(config.capabilities.cross_run_ai_summary)
        self.assertIsNotNone(config.cross_run_adapter)
        self.assertIsNotNone(config.pdf_renderer)

    def test_inside_sales_config_exposes_all_expected_capabilities(self):
        config = get_analytics_app_config('inside-sales')
        self.assertIsNotNone(config)
        assert config is not None
        self.assertTrue(config.capabilities.single_run_report)
        self.assertTrue(config.capabilities.cross_run_analytics)
        self.assertTrue(config.capabilities.pdf_export)
        self.assertTrue(config.capabilities.cross_run_ai_summary)
        self.assertIsNotNone(config.cross_run_adapter)
        self.assertIsNotNone(config.pdf_renderer)

    def test_unknown_app_has_no_registry_config(self):
        self.assertIsNone(get_analytics_app_config('voice-rx'))


if __name__ == '__main__':
    unittest.main()
