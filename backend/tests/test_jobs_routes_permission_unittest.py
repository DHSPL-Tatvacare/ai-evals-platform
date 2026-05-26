"""Per-job-type permission gate tests.

Coverage:
  1. Mapping: required_permissions_for_job returns the declared tuple.
  2. Boot-guard: register_job_handler raises ValueError when required_permissions
     is absent or contains unknown ids.
  3. Route deny (before DB): submit_job raises 403 for a mismatched permission.
     The fake session raises AssertionError on any access, proving the gate fires
     before any DB work.
  4. Route deny for a system job: evaluation:run holder can't submit send-mail.
  5. Gate allows correct permission: ensure_any_permission passes for the right
     holder and owner bypass works.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
import pytest
from fastapi import HTTPException, Response

# ---------------------------------------------------------------------------
# Only stub app.database which is referenced at module level in job_worker.
# Handler-specific imports are lazy (inside function bodies) and don't need
# stubbing for these tests — avoiding stubs prevents sys.modules pollution
# that breaks test_job_worker_unittest.py when both files run in one process.
# ---------------------------------------------------------------------------
_fake_db_mod = ModuleType("app.database")
_fake_db_mod.async_session = None  # type: ignore[attr-defined]
sys.modules.setdefault("app.database", _fake_db_mod)

from app.auth.context import AuthContext  # noqa: E402
from app.auth.permissions import ensure_any_permission  # noqa: E402
from app.services.job_worker import required_permissions_for_job  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth(perms: set[str], *, owner: bool = False) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="test@example.com",
        role_id=uuid.uuid4(),
        is_owner=owner,
        permissions=frozenset(perms),
        app_access=frozenset(),
    )


class _GuardedSession:
    """Session stub that raises AssertionError on any DB access.

    Used to prove the permission gate fires BEFORE any database work.
    """

    def _fail(self, *_a, **_kw):
        raise AssertionError("DB touched before permission gate")

    async def scalar(self, *a, **kw):
        self._fail()

    async def execute(self, *a, **kw):
        self._fail()

    def add(self, *a, **kw):
        self._fail()

    async def commit(self, *a, **kw):
        self._fail()

    async def flush(self, *a, **kw):
        self._fail()

    async def rollback(self, *a, **kw):
        self._fail()


# ---------------------------------------------------------------------------
# 1. Mapping tests (pure, no route call)
# ---------------------------------------------------------------------------

def test_mapping_generate_cross_run_report():
    assert required_permissions_for_job("generate-cross-run-report") == ("report:run",)


def test_mapping_evaluate_batch():
    assert required_permissions_for_job("evaluate-batch") == ("evaluation:run",)


def test_mapping_send_mail():
    assert required_permissions_for_job("send-mail") == ("platform:manage",)


def test_mapping_unknown_job_returns_empty():
    # Unknown job type must return empty tuple (no KeyError).
    assert required_permissions_for_job("does-not-exist") == ()


# ---------------------------------------------------------------------------
# 2. Boot-guard: register_job_handler validation
# ---------------------------------------------------------------------------

def test_register_missing_required_permissions_raises():
    """Omitting required_permissions raises ValueError at decoration time."""
    from app.services.job_worker import register_job_handler

    with pytest.raises(ValueError, match="required_permissions"):
        @register_job_handler("x-test-no-perms-aaa")
        async def _dummy(job_id, params, *, tenant_id, user_id):
            pass


def test_register_invalid_permission_id_raises():
    """A permission id not in VALID_PERMISSIONS raises ValueError."""
    from app.services.job_worker import register_job_handler

    with pytest.raises(ValueError):
        @register_job_handler(
            "x-test-bad-perm-bbb",
            required_permissions=("not:real",),
        )
        async def _dummy2(job_id, params, *, tenant_id, user_id):
            pass


# ---------------------------------------------------------------------------
# 3. Route deny (before DB) — submit_job, wrong permission
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_job_wrong_permission_denies_before_db():
    """Auth holding only evaluation:run is denied on generate-cross-run-report (403).

    The guarded session raises AssertionError if anything reaches the DB,
    so the test also proves the gate fires before any DB access.
    """
    from app.routes.jobs import submit_job
    from app.schemas.job import JobCreate

    auth = _auth({"evaluation:run"})
    db = _GuardedSession()
    body = JobCreate(job_type="generate-cross-run-report", params={"app_id": "voice-rx"})

    with pytest.raises(HTTPException) as exc_info:
        await submit_job(body=body, response=Response(), auth=auth, db=db, idempotency_key_header=None)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 4. Route deny — system job blocked for evaluation:run holder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_job_system_job_denied_to_eval_run_holder():
    """evaluation:run must not unlock send-mail (platform-internal)."""
    from app.routes.jobs import submit_job
    from app.schemas.job import JobCreate

    auth = _auth({"evaluation:run"})
    db = _GuardedSession()
    body = JobCreate(job_type="send-mail", params={})

    with pytest.raises(HTTPException) as exc_info:
        await submit_job(body=body, response=Response(), auth=auth, db=db, idempotency_key_header=None)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 5. Gate allows correct permission and owner bypass
# ---------------------------------------------------------------------------

def test_ensure_any_permission_passes_for_correct_perm():
    auth = _auth({"report:run"})
    # Must not raise
    ensure_any_permission(auth, *required_permissions_for_job("generate-cross-run-report"))


def test_ensure_any_permission_owner_bypasses():
    auth = _auth(set(), owner=True)
    # Owner bypasses regardless of declared permissions
    ensure_any_permission(auth, *required_permissions_for_job("send-mail"))
