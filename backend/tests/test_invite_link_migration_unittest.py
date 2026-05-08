"""Structural smoke for the invite-link lifecycle additive migration.

The repo has no Postgres-bound test harness for alembic migrations, so a
full `upgrade()` / `downgrade()` round-trip is only exercised on a real
database (CI / dev compose). This test pins the migration file's
contract: revision wiring, presence of every DDL the design spec
requires, and the order of CREATE / DROP statements that make
downgrade reversible.

Catches regressions like "someone deleted the CHECK constraint" or
"someone forgot to drop the enum type on downgrade" without standing up
a DB.
"""
import importlib.util
import pathlib
import sys
import unittest
from types import ModuleType


fake_alembic = ModuleType('alembic')
fake_alembic.op = object()
sys.modules.setdefault('alembic', fake_alembic)


_VERSIONS_DIR = (
    pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
)
_MIGRATION_PATH = _VERSIONS_DIR / "0033_invite_link_lifecycle_additive.py"
_PHASE_4_MIGRATION_PATH = _VERSIONS_DIR / "0034_invite_link_drop_is_active.py"


class MigrationStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # ``alembic/versions`` is not a Python package, so import by file path.
        spec = importlib.util.spec_from_file_location(
            "_invite_link_lifecycle_additive_for_test", _MIGRATION_PATH
        )
        assert spec is not None and spec.loader is not None
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def _upgrade_source(self) -> str:
        import inspect

        return inspect.getsource(self.module.upgrade)

    def _downgrade_source(self) -> str:
        import inspect

        return inspect.getsource(self.module.downgrade)

    def test_revision_wiring(self):
        self.assertEqual(
            self.module.revision, "0033_invite_link_lifecycle_additive"
        )
        self.assertEqual(
            self.module.down_revision, "0032_normalize_visibility_defaults"
        )

    def test_upgrade_creates_enum_types_in_platform_schema(self):
        src = self._upgrade_source()
        self.assertIn("CREATE TYPE platform.invite_link_status", src)
        self.assertIn("CREATE TYPE platform.invite_signup_method", src)
        for value in ("'active'", "'revoked'", "'expired'", "'exhausted'"):
            self.assertIn(value, src)
        for value in ("'password'", "'sso'"):
            self.assertIn(value, src)

    def test_upgrade_adds_all_new_columns(self):
        src = self._upgrade_source()
        for col in (
            "ADD COLUMN status platform.invite_link_status",
            "ADD COLUMN revoked_at TIMESTAMPTZ NULL",
            "ADD COLUMN revoked_by UUID NULL",
            "ADD COLUMN revoked_by_email_snapshot VARCHAR(320) NULL",
            "ADD COLUMN created_by_email_snapshot VARCHAR(320) NULL",
            "ADD COLUMN signup_method platform.invite_signup_method",
        ):
            self.assertIn(col, src, msg=f"missing column add: {col}")

    def test_upgrade_changes_created_by_to_set_null(self):
        src = self._upgrade_source()
        self.assertIn("ALTER COLUMN created_by DROP NOT NULL", src)
        self.assertIn(
            "REFERENCES platform.users(id)\n            ON DELETE SET NULL",
            src,
        )

    def test_upgrade_backfills_status_correctly(self):
        src = self._upgrade_source()
        # Revoked first (before expired/exhausted skip them).
        revoked_idx = src.index("SET status = 'revoked'")
        expired_idx = src.index("SET status = 'expired'")
        exhausted_idx = src.index("SET status = 'exhausted'")
        self.assertLess(revoked_idx, expired_idx)
        self.assertLess(expired_idx, exhausted_idx)
        # ``revoked_at`` fallback to ``created_at`` per spec §11.1.
        self.assertIn("COALESCE(revoked_at, created_at)", src)
        # Snapshot backfill via LEFT JOIN — orphan rows must remain
        # listable after creator deletion.
        self.assertIn("created_by_email_snapshot = u.email", src)

    def test_upgrade_adds_check_constraint_after_backfill(self):
        src = self._upgrade_source()
        # CHECK must come AFTER the backfill UPDATEs so existing rows
        # never violate it.
        last_update_idx = src.rfind("SET status =")
        check_idx = src.index("chk_invite_link_revoked_consistency")
        self.assertLess(last_update_idx, check_idx)
        self.assertIn(
            "(status = 'revoked') = (revoked_at IS NOT NULL)", src
        )

    def test_upgrade_creates_uses_table_with_indexes(self):
        src = self._upgrade_source()
        self.assertIn(
            "CREATE TABLE platform.identity_invite_link_uses", src
        )
        for col in (
            "id UUID PRIMARY KEY",
            "invite_link_id UUID NOT NULL",
            "user_id UUID NULL",
            "user_email_snapshot VARCHAR(320) NOT NULL",
            "used_at TIMESTAMPTZ NOT NULL",
            "ip_hash CHAR(64) NULL",
        ):
            self.assertIn(col, src, msg=f"missing _uses column: {col}")
        self.assertIn("ON DELETE CASCADE", src)
        self.assertIn(
            "CREATE INDEX idx_invite_uses_invite_id", src
        )
        self.assertIn(
            "CREATE INDEX idx_invite_uses_user_id", src
        )
        self.assertIn("WHERE user_id IS NOT NULL", src)

    def test_downgrade_reverses_in_opposite_order(self):
        src = self._downgrade_source()
        # Drop the audit table first, then the CHECK, then the columns,
        # then the enum types last (you can't DROP TYPE while a column
        # still references it).
        order = [
            "DROP TABLE IF EXISTS platform.identity_invite_link_uses",
            "DROP CONSTRAINT IF EXISTS chk_invite_link_revoked_consistency",
            "DROP COLUMN IF EXISTS signup_method",
            "DROP COLUMN IF EXISTS status",
            "DROP TYPE IF EXISTS platform.invite_signup_method",
            "DROP TYPE IF EXISTS platform.invite_link_status",
        ]
        positions = [src.index(needle) for needle in order]
        self.assertEqual(positions, sorted(positions))

    def test_downgrade_restores_created_by_to_cascade(self):
        src = self._downgrade_source()
        self.assertIn("ALTER COLUMN created_by SET NOT NULL", src)
        self.assertIn("ON DELETE CASCADE", src)


class Phase4MigrationStructureTests(unittest.TestCase):
    """Pins ``0034_invite_link_drop_is_active`` shape: drops ``is_active``,
    downgrade re-creates it from ``status``."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "_invite_link_drop_is_active_for_test", _PHASE_4_MIGRATION_PATH
        )
        assert spec is not None and spec.loader is not None
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def _upgrade_source(self) -> str:
        import inspect

        return inspect.getsource(self.module.upgrade)

    def _downgrade_source(self) -> str:
        import inspect

        return inspect.getsource(self.module.downgrade)

    def test_revision_wiring(self):
        self.assertEqual(
            self.module.revision, "0034_invite_link_drop_is_active"
        )
        self.assertEqual(
            self.module.down_revision, "0033_invite_link_lifecycle_additive"
        )

    def test_upgrade_drops_is_active_column(self):
        src = self._upgrade_source()
        self.assertIn(
            "ALTER TABLE platform.identity_invite_links DROP COLUMN is_active",
            src,
        )

    def test_downgrade_recreates_and_backfills_is_active(self):
        src = self._downgrade_source()
        # Re-add NOT NULL DEFAULT TRUE so existing rows stay valid.
        self.assertIn("ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE", src)
        # Reconstruct from status — best-effort, lossy.
        self.assertIn("is_active = (status = 'active')", src)


if __name__ == "__main__":
    unittest.main()
