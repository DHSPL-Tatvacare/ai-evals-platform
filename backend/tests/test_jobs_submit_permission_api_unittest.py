"""API-level (TestClient) verification: per-job-type permission gate on POST /api/jobs.

Mounts only the jobs router on a bare FastAPI app and overrides both
``get_auth_context`` and ``get_db`` via dependency_overrides, avoiding any
live DB connection.

The two symbols used as override keys are imported from ``app.routes.jobs``
(the module that binds them to the router) so the override is guaranteed to
hit the right callable.

Rationale for a separate file: ``test_jobs_routes_permission_unittest.py``
stubs ``app.database`` in sys.modules which is incompatible with TestClient
mounting the real router.
"""
from __future__ import annotations

import uuid
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the jobs router module. app.database is imported at module level
# inside jobs.py but only creates a lazy SQLAlchemy engine — no live
# connection occurs at import time, so no DB is required here.
from app.routes import jobs as jobs_routes
from app.auth.context import AuthContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_auth(perms: set[str]) -> AuthContext:
    return AuthContext(
        is_owner=False,
        permissions=frozenset(perms),
        app_access=frozenset({"voice-rx", "inside-sales", "kaira-bot"}),
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="t@e.com",
        role_id=uuid.uuid4(),
    )


class _GuardedSession:
    """Async-session stub that raises AssertionError on any DB access.

    Its presence after the permission gate means any call reaching it is a
    test bug; its presence BEFORE proves the gate fires first.
    """

    def _fail(self, *_a, **_kw):
        raise AssertionError("DB touched before permission gate or unexpectedly")

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


def _guarded_db() -> AsyncGenerator:
    """Dependency override: yield a guarded session."""
    async def _gen():
        yield _GuardedSession()
    return _gen()


def _build_client(perms: set[str]) -> TestClient:
    """Build a TestClient with the jobs router and mocked auth + DB."""
    app = FastAPI()
    app.include_router(jobs_routes.router)

    auth_ctx = _make_auth(perms)

    def _override_auth():
        return auth_ctx

    app.dependency_overrides[jobs_routes.get_auth_context] = _override_auth
    app.dependency_overrides[jobs_routes.get_db] = _guarded_db

    # raise_server_exceptions=False: a 500 from the guarded session
    # (after permission passes) surfaces as HTTP 500, not a raised exception.
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

_CLIENT_EVAL_RUN_ONLY = _build_client({"evaluation:run"})
_CLIENT_REPORT_RUN = _build_client({"report:run"})

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_api_cross_run_denied_for_evaluation_run_only():
    """evaluation:run holder gets 403 on generate-cross-run-report; DB never touched."""
    resp = _CLIENT_EVAL_RUN_ONLY.post(
        "/api/jobs",
        json={"jobType": "generate-cross-run-report", "params": {"app_id": "voice-rx"}},
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", "")
    assert "report:run" in detail, (
        f"Expected 'report:run' in detail, got: {detail!r}"
    )


def test_api_cross_run_report_run_passes_gate():
    """report:run holder clears the permission gate (500 = DB reached after gate = gate passed)."""
    resp = _CLIENT_REPORT_RUN.post(
        "/api/jobs",
        json={"jobType": "generate-cross-run-report", "params": {"app_id": "voice-rx"}},
    )
    # 403 would mean the gate wrongly blocked a valid holder.
    assert resp.status_code != 403, (
        f"report:run holder was incorrectly denied (403): {resp.text}"
    )
    # 500 means execution passed the gate and hit the guarded DB — expected.
    assert resp.status_code == 500, (
        f"Expected 500 (DB guard after gate), got {resp.status_code}: {resp.text}"
    )


def test_api_send_mail_denied_for_evaluation_run_only():
    """evaluation:run holder gets 403 on send-mail (requires platform:manage); DB never touched."""
    resp = _CLIENT_EVAL_RUN_ONLY.post(
        "/api/jobs",
        json={"jobType": "send-mail", "params": {}},
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", "")
    assert "platform:manage" in detail, (
        f"Expected 'platform:manage' in detail, got: {detail!r}"
    )
