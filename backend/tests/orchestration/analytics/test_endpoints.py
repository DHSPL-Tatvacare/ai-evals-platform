"""End-to-end /api/orchestration/analytics route tests.

Live ``db_session`` fixture, override ``get_db`` + ``get_auth_context`` via
dependency_overrides, HTTPX AsyncClient against the ASGI app. Covers the
data-layer scope gate (admin tenant 200 / plain-user tenant 403) and the
app-config gate (hasOrchestration=false 403).
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context
from app.database import get_db
from app.main import app as fastapi_app
from app.models.application import Application
from app.models.tenant import Tenant


async def _seed_tenant(db_session) -> uuid.UUID:
    """A real tenant row so workflow FK inserts succeed."""
    tid = uuid.uuid4()
    db_session.add(
        Tenant(id=tid, name="T", slug=f"t-{uuid.uuid4().hex[:8]}", is_active=True)
    )
    await db_session.flush()
    return tid


def _app_config(has_orchestration: bool) -> dict:
    return {
        "displayName": "X",
        "icon": "i",
        "description": "d",
        "features": {"hasOrchestration": has_orchestration},
    }


async def _seed_app(db_session, *, enabled: bool) -> str:
    slug = f"analytics-ep-{uuid.uuid4().hex[:8]}"
    db_session.add(
        Application(
            id=uuid.uuid4(), slug=slug, display_name="X",
            description="d", config=_app_config(enabled),
        )
    )
    await db_session.flush()
    return slug


def _admin_auth(tenant_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant_id,
        email="admin@orchestration.local", role_id=uuid.uuid4(),
        is_owner=True, permissions=frozenset(),
        app_access=frozenset(),
    )


def _plain_auth(tenant_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant_id,
        email="user@orchestration.local", role_id=uuid.uuid4(),
        is_owner=False, permissions=frozenset({"orchestration:manage"}),
        app_access=frozenset(),
    )


def _insights_auth(tenant_id: uuid.UUID, user_id: uuid.UUID | None = None) -> AuthContext:
    """Read-only insights token: insights:view but NOT orchestration:manage."""
    return AuthContext(
        user_id=user_id or uuid.uuid4(), tenant_id=tenant_id,
        email="viewer@orchestration.local", role_id=uuid.uuid4(),
        is_owner=False, permissions=frozenset({"insights:view"}),
        app_access=frozenset(),
    )


def _no_perm_auth(tenant_id: uuid.UUID) -> AuthContext:
    """Token with NEITHER analytics permission."""
    return AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant_id,
        email="nobody@orchestration.local", role_id=uuid.uuid4(),
        is_owner=False, permissions=frozenset(),
        app_access=frozenset(),
    )


def _override(db_session, auth: AuthContext) -> None:
    async def _g():
        yield db_session
    fastapi_app.dependency_overrides[get_db] = _g
    fastapi_app.dependency_overrides[get_auth_context] = lambda: auth
    db_session.commit = db_session.flush  # type: ignore[assignment]


@pytest_asyncio.fixture
async def client(db_session):
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test",
        ) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)
        fastapi_app.dependency_overrides.pop(get_auth_context, None)


@pytest.mark.asyncio
async def test_overview_admin_tenant_scope_200(db_session, client):
    slug = await _seed_app(db_session, enabled=True)
    _override(db_session, _admin_auth(uuid.uuid4()))
    r = await client.get(f"/api/orchestration/analytics/overview?appId={slug}&scope=tenant")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "runs" in body and "recipients" in body


@pytest.mark.asyncio
async def test_overview_plain_user_tenant_scope_403(db_session, client):
    slug = await _seed_app(db_session, enabled=True)
    _override(db_session, _plain_auth(uuid.uuid4()))
    r = await client.get(f"/api/orchestration/analytics/overview?appId={slug}&scope=tenant")
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_overview_orchestration_disabled_403(db_session, client):
    slug = await _seed_app(db_session, enabled=False)
    _override(db_session, _admin_auth(uuid.uuid4()))
    r = await client.get(f"/api/orchestration/analytics/overview?appId={slug}&scope=tenant")
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_trend_admin_tenant_scope_200(db_session, client):
    slug = await _seed_app(db_session, enabled=True)
    _override(db_session, _admin_auth(uuid.uuid4()))
    r = await client.get(f"/api/orchestration/analytics/trend?appId={slug}&scope=tenant")
    assert r.status_code == 200, r.text
    assert "points" in r.json()


@pytest.mark.asyncio
async def test_trend_orchestration_disabled_403(db_session, client):
    slug = await _seed_app(db_session, enabled=False)
    _override(db_session, _admin_auth(uuid.uuid4()))
    r = await client.get(f"/api/orchestration/analytics/trend?appId={slug}&scope=tenant")
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_overview_insights_view_only_200(db_session, client):
    slug = await _seed_app(db_session, enabled=True)
    _override(db_session, _insights_auth(uuid.uuid4()))
    r = await client.get(f"/api/orchestration/analytics/overview?appId={slug}")
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_overview_no_permission_403(db_session, client):
    slug = await _seed_app(db_session, enabled=True)
    _override(db_session, _no_perm_auth(uuid.uuid4()))
    r = await client.get(f"/api/orchestration/analytics/overview?appId={slug}")
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_run_report_admin_200(db_session, client, seed_orchestration_run):
    slug = await _seed_app(db_session, enabled=True)
    tenant = await _seed_tenant(db_session)
    seeded = await seed_orchestration_run(
        tenant_id=tenant, app_id=slug,
        recipients=[
            {"recipient_id": "r0", "channel": "voice",
             "action_type": "bolna_answered", "bucket": "positive",
             "voice_duration_sec": 90},
        ],
    )
    _override(db_session, _admin_auth(tenant))
    r = await client.get(
        f"/api/orchestration/analytics/runs/{seeded['run_id']}/report?appId={slug}&scope=tenant"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["runId"] == str(seeded["run_id"])
    assert body["recipientsTotalCount"] == 1
    assert any(c["capability"] == "voice" for c in body["channels"])


@pytest.mark.asyncio
async def test_run_report_unknown_run_404(db_session, client):
    slug = await _seed_app(db_session, enabled=True)
    _override(db_session, _admin_auth(uuid.uuid4()))
    r = await client.get(
        f"/api/orchestration/analytics/runs/{uuid.uuid4()}/report?appId={slug}&scope=tenant"
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_run_report_scope_leak_non_owner_mine_404_zero_recipients(
    db_session, client, seed_orchestration_run
):
    # Run owned by SYSTEM_USER_ID (default created_by), private visibility, in the
    # caller's tenant. A non-owner caller with scope=mine must NOT see it.
    slug = await _seed_app(db_session, enabled=True)
    caller_tenant = await _seed_tenant(db_session)
    seeded = await seed_orchestration_run(
        tenant_id=caller_tenant, app_id=slug,
        recipients=[
            {"recipient_id": "secret", "channel": "voice",
             "action_type": "bolna_answered", "bucket": "positive",
             "attributes": {"name": "Private Patient"}},
        ],
    )
    _override(db_session, _insights_auth(caller_tenant))
    r = await client.get(
        f"/api/orchestration/analytics/runs/{seeded['run_id']}/report?appId={slug}&scope=mine"
    )
    assert r.status_code == 404, r.text
    assert "Private Patient" not in r.text
    assert "recipients" not in r.json()


@pytest.mark.asyncio
async def test_export_pdf_admin_200_application_pdf(
    db_session, client, seed_orchestration_run, monkeypatch
):
    slug = await _seed_app(db_session, enabled=True)
    tenant = await _seed_tenant(db_session)
    seeded = await seed_orchestration_run(
        tenant_id=tenant, app_id=slug,
        recipients=[
            {"recipient_id": "r0", "channel": "voice",
             "action_type": "bolna_answered", "bucket": "positive"},
        ],
    )

    calls: dict = {}

    async def _fake_render(*, print_path, auth, log_id, pdf_meta=None):
        calls["print_path"] = print_path
        calls["pdf_meta"] = pdf_meta
        return b"%PDF-1.7 fake"

    monkeypatch.setattr(
        "app.routes.orchestration_analytics._render_pdf_via_print_route", _fake_render
    )
    _override(db_session, _admin_auth(tenant))
    r = await client.get(
        f"/api/orchestration/analytics/runs/{seeded['run_id']}/export-pdf?appId={slug}&scope=tenant"
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == b"%PDF-1.7 fake"
    assert str(seeded["run_id"]) in calls["print_path"]
    assert f"appId={slug}" in calls["print_path"]
    assert "scope=tenant" in calls["print_path"]
    assert calls["print_path"].startswith("/print/campaign-runs/")


@pytest.mark.asyncio
async def test_export_pdf_scope_leak_non_owner_mine_404_render_not_called(
    db_session, client, seed_orchestration_run, monkeypatch
):
    # Run owned by SYSTEM_USER_ID, private, in caller tenant. A non-owner with
    # scope=mine must get 404 BEFORE any PDF render fires (no recipient leak).
    slug = await _seed_app(db_session, enabled=True)
    caller_tenant = await _seed_tenant(db_session)
    seeded = await seed_orchestration_run(
        tenant_id=caller_tenant, app_id=slug,
        recipients=[
            {"recipient_id": "secret", "channel": "voice",
             "action_type": "bolna_answered", "bucket": "positive",
             "attributes": {"name": "Private Patient"}},
        ],
    )

    render_called = {"value": False}

    async def _fake_render(*, print_path, auth, log_id, pdf_meta=None):
        render_called["value"] = True
        return b"%PDF leak"

    monkeypatch.setattr(
        "app.routes.orchestration_analytics._render_pdf_via_print_route", _fake_render
    )
    _override(db_session, _insights_auth(caller_tenant))
    r = await client.get(
        f"/api/orchestration/analytics/runs/{seeded['run_id']}/export-pdf?appId={slug}&scope=mine"
    )
    assert r.status_code == 404, r.text
    assert render_called["value"] is False
    assert "Private Patient" not in r.text


@pytest.mark.asyncio
async def test_export_pdf_no_permission_403(db_session, client, monkeypatch):
    slug = await _seed_app(db_session, enabled=True)

    async def _fake_render(*, print_path, auth, log_id, pdf_meta=None):
        raise AssertionError("render must not run without permission")

    monkeypatch.setattr(
        "app.routes.orchestration_analytics._render_pdf_via_print_route", _fake_render
    )
    _override(db_session, _no_perm_auth(uuid.uuid4()))
    r = await client.get(
        f"/api/orchestration/analytics/runs/{uuid.uuid4()}/export-pdf?appId={slug}&scope=tenant"
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_signals_returns_empty_pre_phase3(db_session, client):
    slug = await _seed_app(db_session, enabled=True)
    _override(db_session, _admin_auth(uuid.uuid4()))
    r = await client.get(f"/api/orchestration/analytics/signals?appId={slug}")
    assert r.status_code == 200, r.text
    assert r.json()["signals"] == []
