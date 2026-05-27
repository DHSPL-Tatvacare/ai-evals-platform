"""End-to-end /api/cost/entities app_id resolution tests.

Mirrors the cost-modality route test harness: live ``db_session`` fixture,
override ``get_db`` + ``get_auth_context``, HTTPX ``AsyncClient`` against the
ASGI app.

Locks the EntityRow app_id collapse:
- single distinct app_id across all fact rows for an owner → that app_id
- multiple distinct app_ids for the same owner → null (None)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context
from app.constants import SYSTEM_USER_ID
from app.database import get_db
from app.main import app as fastapi_app
from app.models.cost import FactLlmGeneration
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
        email='cost-entities-app-id@cost.local',
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
        name=f'cost-ent-{tenant_id.hex[:8]}',
        slug=f'cost-ent-{tenant_id.hex[:8]}',
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


def _fact(tenant_id, owner_id, app_id, *, cost='0.50', input_tokens=100):
    return FactLlmGeneration(
        id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        tenant_id=tenant_id,
        user_id=SYSTEM_USER_ID,
        app_id=app_id,
        owner_type='eval_run',
        owner_id=owner_id,
        provider='openai',
        model='gpt-4o-mini',
        input_tokens=input_tokens,
        cost_usd=Decimal(cost),
        modality_details={},
    )


@pytest.mark.asyncio
async def test_single_app_owner_returns_app_id(client, db_session, route_tenant_id):
    # Two rows, same owner, same app_id → EntityRow.appId == 'inside-sales'.
    owner_id = uuid.uuid4()
    db_session.add(_fact(route_tenant_id, owner_id, 'inside-sales', cost='1.00', input_tokens=500))
    db_session.add(_fact(route_tenant_id, owner_id, 'inside-sales', cost='2.00', input_tokens=1000))
    await db_session.flush()

    r = await client.get('/api/cost/entities?range=24h&owner_type=eval_run')
    assert r.status_code == 200, r.text
    body = r.json()

    items = [i for i in body['items'] if i['ownerId'] == str(owner_id)]
    assert len(items) == 1, f'expected exactly one item for owner; got {items}'
    item = items[0]

    assert item['appId'] == 'inside-sales'
    assert item['callCount'] == 2
    assert abs(item['costUsd'] - 3.0) < 1e-6


@pytest.mark.asyncio
async def test_multi_app_owner_returns_null_app_id(client, db_session, route_tenant_id):
    # Two rows, same owner, different app_ids → EntityRow.appId is None.
    owner_id = uuid.uuid4()
    db_session.add(_fact(route_tenant_id, owner_id, 'inside-sales', cost='1.00', input_tokens=400))
    db_session.add(_fact(route_tenant_id, owner_id, 'kaira-bot', cost='1.00', input_tokens=400))
    await db_session.flush()

    r = await client.get('/api/cost/entities?range=24h&owner_type=eval_run')
    assert r.status_code == 200, r.text
    body = r.json()

    items = [i for i in body['items'] if i['ownerId'] == str(owner_id)]
    assert len(items) == 1, f'expected exactly one item for owner; got {items}'
    item = items[0]

    assert item['appId'] is None
    assert item['callCount'] == 2
    assert abs(item['costUsd'] - 2.0) < 1e-6
