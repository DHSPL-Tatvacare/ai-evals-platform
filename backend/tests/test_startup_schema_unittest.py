import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_BOOTSTRAP_PATH = ROOT / 'app' / 'startup_schema.py'


class StartupSchemaTests(unittest.TestCase):
    def test_schema_bootstrap_serializes_concurrent_startup(self):
        contents = SCHEMA_BOOTSTRAP_PATH.read_text()

        self.assertIn('pg_advisory_xact_lock', contents)

    def test_schema_bootstrap_repairs_settings_scope_indexes_as_unique(self):
        contents = SCHEMA_BOOTSTRAP_PATH.read_text()

        expected_snippets = [
            "DROP INDEX IF EXISTS uq_settings_private_scope",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_settings_private_scope",
            "DROP INDEX IF EXISTS uq_settings_shared_scope",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_settings_shared_scope",
        ]

        for snippet in expected_snippets:
            self.assertIn(snippet, contents)

    def test_schema_bootstrap_adds_evaluator_seed_identity_columns(self):
        contents = SCHEMA_BOOTSTRAP_PATH.read_text()

        self.assertIn("ALTER TABLE evaluators ADD COLUMN IF NOT EXISTS seed_key VARCHAR(120)", contents)
        self.assertIn("ALTER TABLE evaluators ADD COLUMN IF NOT EXISTS seed_variant VARCHAR(50)", contents)
