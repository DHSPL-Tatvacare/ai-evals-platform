"""Unit tests for compute_invite_status plus row-local invite helpers.

Truth-table coverage across the four lifecycle states, plus the small pure
helpers that Phase 4 still leaves on the model/service layer.
"""
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import ModuleType

# The test harness avoids importing the real DB stack.
fake_database = ModuleType('app.database')
fake_database.get_db = None
sys.modules.setdefault('app.database', fake_database)

from app.models.invite_link import IdentityInviteLink, InviteStatus
from app.services.invite_links import compute_invite_status, hash_ip


_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
_FUTURE = _NOW + timedelta(hours=1)
_PAST = _NOW - timedelta(hours=1)


class ComputeInviteStatusTests(unittest.TestCase):
    def test_active_when_unrevoked_unexpired_unfilled(self):
        self.assertEqual(
            compute_invite_status(
                is_revoked=False,
                expires_at=_FUTURE,
                max_uses=None,
                uses_count=0,
                now=_NOW,
            ),
            InviteStatus.active,
        )

    def test_revoked_takes_precedence_over_expiry(self):
        # Even a passed expiry date does not change the visible state once
        # an admin has revoked: the audit story is "we stopped this link."
        self.assertEqual(
            compute_invite_status(
                is_revoked=True,
                expires_at=_PAST,
                max_uses=10,
                uses_count=10,
                now=_NOW,
            ),
            InviteStatus.revoked,
        )

    def test_expired_when_expires_at_in_past(self):
        self.assertEqual(
            compute_invite_status(
                is_revoked=False,
                expires_at=_PAST,
                max_uses=None,
                uses_count=0,
                now=_NOW,
            ),
            InviteStatus.expired,
        )

    def test_expired_at_exact_boundary(self):
        # ``expires_at <= now`` is expired — bias to safety, no off-by-one.
        self.assertEqual(
            compute_invite_status(
                is_revoked=False,
                expires_at=_NOW,
                max_uses=None,
                uses_count=0,
                now=_NOW,
            ),
            InviteStatus.expired,
        )

    def test_exhausted_when_uses_hit_max(self):
        self.assertEqual(
            compute_invite_status(
                is_revoked=False,
                expires_at=_FUTURE,
                max_uses=3,
                uses_count=3,
                now=_NOW,
            ),
            InviteStatus.exhausted,
        )

    def test_unlimited_max_uses_never_exhausts(self):
        self.assertEqual(
            compute_invite_status(
                is_revoked=False,
                expires_at=_FUTURE,
                max_uses=None,
                uses_count=10_000,
                now=_NOW,
            ),
            InviteStatus.active,
        )


class IsRevokedPropertyTests(unittest.TestCase):
    """``is_revoked`` is the only model-level lifecycle helper post-Phase-4.
    Status itself is read directly from the column."""

    def _make(self, **overrides) -> IdentityInviteLink:
        invite = IdentityInviteLink(
            tenant_id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            token_hash="x" * 64,
            role_id=uuid.uuid4(),
            max_uses=None,
            uses_count=0,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        invite.revoked_at = None
        for key, value in overrides.items():
            setattr(invite, key, value)
        return invite

    def test_unrevoked_invite_is_not_revoked(self):
        self.assertFalse(self._make().is_revoked)

    def test_invite_with_revoked_at_is_revoked(self):
        invite = self._make(revoked_at=datetime.now(timezone.utc))
        self.assertTrue(invite.is_revoked)


class HashIpTests(unittest.TestCase):
    def test_hash_is_deterministic_per_tenant(self):
        tenant = uuid.uuid4()
        a = hash_ip("192.0.2.1", tenant)
        b = hash_ip("192.0.2.1", tenant)
        self.assertEqual(a, b)
        assert a is not None
        self.assertEqual(len(a), 64)

    def test_hash_differs_across_tenants(self):
        a = hash_ip("192.0.2.1", uuid.uuid4())
        b = hash_ip("192.0.2.1", uuid.uuid4())
        self.assertNotEqual(a, b)

    def test_none_input_returns_none(self):
        self.assertIsNone(hash_ip(None, uuid.uuid4()))
        self.assertIsNone(hash_ip("", uuid.uuid4()))


if __name__ == "__main__":
    unittest.main()
