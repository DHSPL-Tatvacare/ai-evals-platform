"""Connection test-probe dispatch: wati/bolna reuse the adapter list calls."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.orchestration.connections.health import probe

_WATI_LIST = "app.services.orchestration.adapters.wati.WatiAdapter.list_message_templates"
_BOLNA_LIST = "app.services.orchestration.adapters.bolna.BolnaAdapter.list_agents"


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
