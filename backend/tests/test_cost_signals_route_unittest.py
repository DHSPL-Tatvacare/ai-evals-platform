"""End-to-end /api/cost/signals route tests.

Mirrors the cost-modality route test harness: live ``db_session`` fixture,
override ``get_db`` + ``get_auth_context``, HTTPX ``AsyncClient`` against the
ASGI app.

Covers the latest-snapshot read:
- no snapshot for the tenant returns an empty signals list
- a stored snapshot maps through, skipping malformed entries
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context
from app.constants import SYSTEM_USER_ID
from app.database import get_db
from app.main import app as fastapi_app
from app.models.cost import CostSignalSnapshot
from app.models.tenant import Tenant


def _override_db(db_session):
    async def _g():
        yield db_session
    fastapi_app.dependency_overrides[get_db] = _g
    db_session.commit = db_session.flush  # type: ignore[assignment]


def _make_auth(tenant_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        user_id=SYSTEM_USER_ID,
        tenant_id=tenant_id,
        email='cost-signals-route@cost.local',
        role_id=uuid.uuid4(),
        is_owner=True,
        permissions=frozenset(),
        app_access=frozenset({'voice-rx', 'kaira-bot', 'inside-sales'}),
    )


def _override_auth(auth: AuthContext):
    fastapi_app.dependency_overrides[get_auth_context] = lambda: auth


@pytest_asyncio.fixture
async def route_tenant_id(db_session) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    db_session.add(Tenant(
        id=tenant_id,
        name=f'cost-sig-{tenant_id.hex[:8]}',
        slug=f'cost-sig-{tenant_id.hex[:8]}',
        is_active=True,
    ))
    await db_session.flush()
    return tenant_id


@pytest_asyncio.fixture
async def client(db_session, route_tenant_id):
    _override_db(db_session)
    _override_auth(_make_auth(route_tenant_id))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app), base_url='http://test',
        ) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)
        fastapi_app.dependency_overrides.pop(get_auth_context, None)


@pytest.mark.asyncio
async def test_no_snapshot_returns_empty(client):
    r = await client.get('/api/cost/signals')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['signals'] == []
    assert body['generatedAt'] is None
    assert body['model'] is None
    assert body['period'] is None


@pytest.mark.asyncio
async def test_latest_snapshot_maps_and_skips_malformed(client, db_session, route_tenant_id):
    db_session.add(CostSignalSnapshot(
        id=uuid.uuid4(),
        tenant_id=route_tenant_id,
        generated_at=datetime.now(timezone.utc),
        model='gpt-5.4',
        period='30d',
        signals=[
            {'severity': 'warning', 'title': 'Spend up', 'detail': 'Cost rose 20%', 'metric': {'delta': 0.2}},
            {'severity': 'info', 'title': 'Stable', 'detail': 'No anomalies'},
            {'severity': 'critical'},  # malformed: missing title/detail -> skipped
            'not-a-dict',              # malformed -> skipped
        ],
    ))
    await db_session.flush()

    r = await client.get('/api/cost/signals')
    assert r.status_code == 200, r.text
    body = r.json()

    assert body['model'] == 'gpt-5.4'
    assert body['period'] == '30d'
    assert body['generatedAt'] is not None

    titles = [s['title'] for s in body['signals']]
    assert titles == ['Spend up', 'Stable']
    assert body['signals'][0]['metric'] == {'delta': 0.2}
    assert body['signals'][1]['metric'] is None
