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
async def test_signals_returns_empty_pre_phase3(db_session, client):
    slug = await _seed_app(db_session, enabled=True)
    _override(db_session, _admin_auth(uuid.uuid4()))
    r = await client.get(f"/api/orchestration/analytics/signals?appId={slug}")
    assert r.status_code == 200, r.text
    assert r.json()["signals"] == []
