import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / 'app' / 'main.py'


class StartupNormalizationTests(unittest.TestCase):
    def test_startup_normalizes_legacy_visibility_values_to_shared(self):
        contents = MAIN_PATH.read_text()

        expected_updates = [
            "UPDATE settings SET visibility = 'SHARED' WHERE visibility = 'APP'",
            "UPDATE prompts SET visibility = 'SHARED' WHERE visibility = 'APP'",
            "UPDATE schemas SET visibility = 'SHARED' WHERE visibility = 'APP'",
            "UPDATE evaluators SET visibility = 'SHARED' WHERE visibility = 'APP'",
            "UPDATE eval_runs SET visibility = 'SHARED' WHERE visibility = 'APP'",
        ]

        for statement in expected_updates:
            self.assertIn(statement, contents)

    def test_startup_normalizes_legacy_role_permissions_to_canonical_catalog(self):
        contents = MAIN_PATH.read_text()

        expected_rewrites = [
            "SELECT role_id, 'evaluation:run'",
            "WHERE permission = 'eval:run'",
            "SELECT role_id, 'evaluation:export'",
            "WHERE permission = 'eval:export'",
            "SELECT role_id, 'asset:create'",
            "WHERE permission = 'resource:create'",
            "SELECT role_id, 'asset:edit'",
            "WHERE permission = 'resource:edit'",
            "SELECT role_id, 'asset:delete'",
            "WHERE permission = 'resource:delete'",
            "SELECT role_id, 'insights:view'",
            "WHERE permission = 'analytics:view'",
            "SELECT role_id, 'configuration:edit'",
            "WHERE permission = 'settings:edit'",
            "SELECT role_id, 'invite_link:manage'",
            "WHERE permission = 'user:invite'",
            "SELECT role_id, 'evaluation:cancel'",
            "SELECT role_id, 'evaluation:delete'",
            "WHERE permission = 'eval:delete'",
            'tenant:settings',
            'evaluator:promote',
            'ON CONFLICT ON CONSTRAINT uq_role_permission DO NOTHING',
        ]

        for snippet in expected_rewrites:
            self.assertIn(snippet, contents)
