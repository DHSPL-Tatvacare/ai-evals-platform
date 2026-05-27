"""End-to-end /api/cost/modality route tests.

Mirrors the dataset-routes test pattern: live ``db_session`` fixture, override
``get_db`` and ``get_auth_context`` via FastAPI dependency_overrides, HTTPX
``AsyncClient`` against the ASGI app.

Covers the cost-by-modality breakdown:
- text-only data (empty/missing modality_details) returns a single text slice
- audio_tokens in modality_details surfaces an audio slice with text = total - audio
- every slice is flagged estimated, cost splits proportionally to tokens
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

APP_ID = 'inside-sales'


def _override_db(db_session):
    async def _g():
        yield db_session
    fastapi_app.dependency_overrides[get_db] = _g
    db_session.commit = db_session.flush  # type: ignore[assignment]


def _make_auth(tenant_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        user_id=SYSTEM_USER_ID,
        tenant_id=tenant_id,
        email='cost-modality-route@cost.local',
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
        name=f'cost-mod-{tenant_id.hex[:8]}',
        slug=f'cost-mod-{tenant_id.hex[:8]}',
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


def _fact(tenant_id, *, input_tokens, cost, modality_details):
    """A minimal fact row. total_tokens is a persisted computed column driven by
    the component token columns, so we drive it via input_tokens here."""
    return FactLlmGeneration(
        id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        tenant_id=tenant_id,
        user_id=SYSTEM_USER_ID,
        app_id=APP_ID,
        owner_type='chat_session',
        owner_id=uuid.uuid4(),
        provider='openai',
        model='gpt-4o-mini',
        input_tokens=input_tokens,
        cost_usd=Decimal(str(cost)),
        modality_details=modality_details,
    )


@pytest.mark.asyncio
async def test_modality_splits_audio_and_text(client, db_session, route_tenant_id):
    # Row A: pure text, 1000 tokens, $1.00, empty modality_details.
    # Row B: 1000 tokens total of which 300 are audio, $1.00, audio in JSONB.
    db_session.add(_fact(route_tenant_id, input_tokens=1000, cost='1.00', modality_details={}))
    db_session.add(_fact(
        route_tenant_id, input_tokens=1000, cost='1.00',
        modality_details={'audio_tokens': 300, 'cached_tokens': 0},
    ))
    await db_session.flush()

    r = await client.get(f'/api/cost/modality?range=24h&app_id={APP_ID}')
    assert r.status_code == 200, r.text
    body = r.json()

    assert body['totalTokens'] == 2000
    assert abs(body['totalCostUsd'] - 2.0) < 1e-6

    by_modality = {s['modality']: s for s in body['modalities']}
    assert set(by_modality) == {'text', 'audio'}

    # audio = 300 (only from row B); text = total - audio = 2000 - 300 = 1700.
    assert by_modality['audio']['tokens'] == 300
    assert by_modality['text']['tokens'] == 1700

    # every slice flagged as an estimate.
    assert all(s['estimated'] is True for s in body['modalities'])

    # cost splits proportionally to tokens: total_cost * tokens / total_tokens.
    assert abs(by_modality['audio']['costUsd'] - (2.0 * 300 / 2000)) < 1e-6
    assert abs(by_modality['text']['costUsd'] - (2.0 * 1700 / 2000)) < 1e-6

    # slices ordered by tokens desc.
    assert body['modalities'][0]['modality'] == 'text'

    assert 'computedAt' in body


@pytest.mark.asyncio
async def test_text_only_data_returns_single_text_slice(client, db_session, route_tenant_id):
    # Mix of empty {}, JSON-null modality_details, and a zeroed audio key — all text.
    db_session.add(_fact(route_tenant_id, input_tokens=500, cost='0.50', modality_details={}))
    db_session.add(_fact(route_tenant_id, input_tokens=500, cost='0.50', modality_details=None))
    db_session.add(_fact(
        route_tenant_id, input_tokens=500, cost='0.50',
        modality_details={'audio_tokens': 0, 'cached_tokens': 0},
    ))
    await db_session.flush()

    r = await client.get(f'/api/cost/modality?range=24h&app_id={APP_ID}')
    assert r.status_code == 200, r.text
    body = r.json()

    assert body['totalTokens'] == 1500
    assert [s['modality'] for s in body['modalities']] == ['text']
    assert body['modalities'][0]['tokens'] == 1500
    assert body['modalities'][0]['estimated'] is True
    assert abs(body['modalities'][0]['costUsd'] - 1.5) < 1e-6
