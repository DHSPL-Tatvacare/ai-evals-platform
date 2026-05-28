"""Scalar API reference route — dev-only gating.

The interactive reference at /api/docs is served only when APP_ENVIRONMENT is a
dev value (local/development). In production the route returns 404 so the spec
surface is never exposed there. No DB, no auth: the gate is environment-only.
"""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from app import config
from app.main import app as fastapi_app


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fastapi_app), base_url='http://test',
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_scalar_reference_served_in_dev(client, monkeypatch):
    monkeypatch.setattr(config.settings, 'APP_ENVIRONMENT', 'local')
    r = await client.get('/api/docs')
    assert r.status_code == 200
    assert 'text/html' in r.headers['content-type']
    assert 'scalar' in r.text.lower()
    assert '/openapi.json' in r.text


@pytest.mark.asyncio
async def test_scalar_reference_hidden_in_production(client, monkeypatch):
    monkeypatch.setattr(config.settings, 'APP_ENVIRONMENT', 'production')
    r = await client.get('/api/docs')
    assert r.status_code == 404
