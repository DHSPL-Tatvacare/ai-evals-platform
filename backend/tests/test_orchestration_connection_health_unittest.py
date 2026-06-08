"""Connection test-probe dispatch: wati/bolna reuse the adapter list calls."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.orchestration.connections.health import probe

_WATI_LIST = "app.services.orchestration.adapters.wati.WatiAdapter.list_message_templates"
_BOLNA_LIST = "app.services.orchestration.adapters.bolna.BolnaAdapter.list_agents"
_HTTPX_POST = "httpx.AsyncClient.post"

_LSQ_CONFIG = {
    "region_host": "https://api-in21.leadsquared.com/v2",
    "access_key": "ak",
    "secret_key": "sk",
}


@pytest.mark.asyncio
async def test_probe_unknown_provider_still_fails():
    res = await probe("mailchimp", {})
    assert res["ok"] is False
    assert "unknown provider" in res["detail"]


@pytest.mark.asyncio
async def test_probe_wati_ok_when_templates_reachable():
    with patch(_WATI_LIST, new=AsyncMock(return_value=[{"name": "a"}, {"name": "b"}])):
        res = await probe("wati", {"base_url": "x", "wati_tenant_id": "1", "api_token": "k"})
    assert res["ok"] is True
    assert "2 template" in res["detail"]


@pytest.mark.asyncio
async def test_probe_wati_fails_and_surfaces_vendor_error():
    with patch(_WATI_LIST, new=AsyncMock(side_effect=RuntimeError("WATI 401: bad token"))):
        res = await probe("wati", {})
    assert res["ok"] is False
    assert "WATI 401" in res["detail"]


@pytest.mark.asyncio
async def test_probe_bolna_ok_when_agents_reachable():
    with patch(_BOLNA_LIST, new=AsyncMock(return_value=[{"id": "a"}])):
        res = await probe("bolna", {"api_key": "k"})
    assert res["ok"] is True
    assert "1 agent" in res["detail"]


@pytest.mark.asyncio
async def test_probe_bolna_fails_and_surfaces_vendor_error():
    with patch(_BOLNA_LIST, new=AsyncMock(side_effect=RuntimeError("Bolna 403: forbidden"))):
        res = await probe("bolna", {})
    assert res["ok"] is False
    assert "Bolna 403" in res["detail"]


@pytest.mark.asyncio
async def test_probe_lsq_ok_on_2xx():
    resp = SimpleNamespace(status_code=200, text="{}")
    with patch(_HTTPX_POST, new=AsyncMock(return_value=resp)):
        res = await probe("lsq", _LSQ_CONFIG)
    assert res["ok"] is True
    assert "200" in res["detail"]


@pytest.mark.asyncio
async def test_probe_lsq_fails_on_401():
    resp = SimpleNamespace(status_code=401, text="invalid key")
    with patch(_HTTPX_POST, new=AsyncMock(return_value=resp)):
        res = await probe("lsq", _LSQ_CONFIG)
    assert res["ok"] is False
    assert "401" in res["detail"]


@pytest.mark.asyncio
async def test_probe_lsq_fails_fast_on_missing_creds_without_network():
    post = AsyncMock()
    with patch(_HTTPX_POST, new=post):
        res = await probe("lsq", {"region_host": "https://x"})
    assert res["ok"] is False
    post.assert_not_called()
