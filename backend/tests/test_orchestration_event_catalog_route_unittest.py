"""GET /api/orchestration/event-catalog — canonical event names gated by workflow_type."""
from __future__ import annotations

import uuid

import httpx
import pytest

from app.auth import AuthContext, get_auth_context
from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
from app.database import get_db
from app.main import app

CATALOG = "/api/orchestration/event-catalog"


def _override(db_session):
    async def _db():
        yield db_session
    app.dependency_overrides[get_db] = _db

    async def _auth():
        return AuthContext(
            user_id=SYSTEM_USER_ID, tenant_id=SYSTEM_TENANT_ID,
            email="t@example.com", role_id=uuid.uuid4(), is_owner=True,
            permissions=frozenset(), app_access=frozenset(),
        )
    app.dependency_overrides[get_auth_context] = _auth


def _clear():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_auth_context, None)


@pytest.mark.asyncio
async def test_catalog_requires_auth(db_session):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get(f"{CATALOG}?workflowType=crm")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_catalog_crm_events(db_session):
    _override(db_session)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get(f"{CATALOG}?workflowType=crm")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["workflowType"] == "crm"
        assert "crm.lead.created" in body["events"]
        assert all(e.startswith("crm.") for e in body["events"])
    finally:
        _clear()


@pytest.mark.asyncio
async def test_catalog_clinical_events(db_session):
    _override(db_session)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get(f"{CATALOG}?workflowType=clinical")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "clinical.program.enrolled" in body["events"]
    finally:
        _clear()


@pytest.mark.asyncio
async def test_catalog_uppercase_returns_empty(db_session):
    _override(db_session)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get(f"{CATALOG}?workflowType=CRM")
        assert r.status_code == 200, r.text
        assert r.json()["events"] == []
    finally:
        _clear()
