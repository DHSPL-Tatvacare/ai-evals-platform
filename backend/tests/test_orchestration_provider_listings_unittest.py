"""Provider-listing cache behavior — single-flight, long TTL, graceful 429 fallback.

No live WATI. The adapter's ``list_message_templates`` is monkeypatched with a
call-counting stub so we assert the inspector-open burst collapses to one fetch.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

import app.services.orchestration.api.provider_listings as pl
from app.services.orchestration.adapters.wati import WatiServiceError


@pytest.fixture(autouse=True)
def _clear_cache():
    pl._CACHE.clear()
    pl._LOCKS.clear()
    yield
    pl._CACHE.clear()
    pl._LOCKS.clear()


_TEMPLATES = [{"name": "document_approved_latest", "parameters": ["name", "documentType"]}]


def _patch(monkeypatch, *, fetch_impl):
    async def _load_connection(_db, *, tenant_id, app_id, connection_id, expected_provider):  # noqa: ARG001
        return {"base_url": "https://x", "wati_tenant_id": "1", "api_token": "t"}

    monkeypatch.setattr(pl, "_load_connection", _load_connection)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.wati.WatiAdapter.list_message_templates",
        fetch_impl,
    )


@pytest.mark.asyncio
async def test_concurrent_fetches_single_flight_one_upstream_call(monkeypatch):
    calls = {"n": 0}

    async def _impl(self, connection):  # noqa: ARG001
        calls["n"] += 1
        await asyncio.sleep(0)  # yield so both coroutines are in flight
        return list(_TEMPLATES)

    _patch(monkeypatch, fetch_impl=_impl)
    cid = uuid.uuid4()

    async def _call():
        return await pl._fetch_wati_templates_cached(
            object(), tenant_id=uuid.uuid4(), app_id="inside-sales", connection_id=cid,
        )

    results = await asyncio.gather(_call(), _call(), _call())
    assert calls["n"] == 1  # single-flight coalesced the burst
    for items, error in results:
        assert error is None
        assert items == _TEMPLATES


@pytest.mark.asyncio
async def test_second_call_within_ttl_hits_cache(monkeypatch):
    calls = {"n": 0}

    async def _impl(self, connection):  # noqa: ARG001
        calls["n"] += 1
        return list(_TEMPLATES)

    _patch(monkeypatch, fetch_impl=_impl)
    cid = uuid.uuid4()
    kw = dict(tenant_id=uuid.uuid4(), app_id="inside-sales", connection_id=cid)
    await pl._fetch_wati_templates_cached(object(), **kw)
    await pl._fetch_wati_templates_cached(object(), **kw)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_429_falls_back_to_last_known_good(monkeypatch):
    state = {"fail": False}

    async def _impl(self, connection):  # noqa: ARG001
        if state["fail"]:
            raise WatiServiceError("WATI 429: {'text': 'Rate limit exceeded'}")
        return list(_TEMPLATES)

    _patch(monkeypatch, fetch_impl=_impl)
    cid = uuid.uuid4()
    kw = dict(tenant_id=uuid.uuid4(), app_id="inside-sales", connection_id=cid)

    items, error = await pl._fetch_wati_templates_cached(object(), **kw)
    assert items == _TEMPLATES and error is None

    state["fail"] = True
    items, error = await pl._fetch_wati_templates_cached(object(), refresh=True, **kw)
    # Picker stays populated; soft, friendly copy — never the raw "WATI 429".
    assert items == _TEMPLATES
    assert error is not None and "rate-limit" in error.lower()
    assert "429" not in error


@pytest.mark.asyncio
async def test_429_with_no_cache_returns_friendly_error(monkeypatch):
    async def _impl(self, connection):  # noqa: ARG001
        raise WatiServiceError("WATI 429: {'text': 'Rate limit exceeded'}")

    _patch(monkeypatch, fetch_impl=_impl)
    items, error = await pl._fetch_wati_templates_cached(
        object(), tenant_id=uuid.uuid4(), app_id="inside-sales", connection_id=uuid.uuid4(),
    )
    assert items == []
    assert "429" not in (error or "")
    assert "rate-limit" in (error or "").lower()


@pytest.mark.asyncio
async def test_get_agent_variables_shares_template_cache(monkeypatch):
    """Variable-mapping introspection must not fire a second upstream fetch."""
    calls = {"n": 0}

    async def _impl(self, connection):  # noqa: ARG001
        calls["n"] += 1
        return list(_TEMPLATES)

    _patch(monkeypatch, fetch_impl=_impl)
    cid = uuid.uuid4()
    tid = uuid.uuid4()

    class _Row:
        provider = "wati"
        app_id = "inside-sales"
        config_encrypted = b""

    async def _scalar(_stmt):
        return _Row()

    monkeypatch.setattr(pl.crypto, "decrypt", lambda _b: {"base_url": "x"})

    # Prime the picker cache.
    await pl._fetch_wati_templates_cached(
        object(), tenant_id=tid, app_id="inside-sales", connection_id=cid,
    )

    class _DB:
        scalar = staticmethod(_scalar)

    out = await pl.get_agent_variables(
        _DB(), tenant_id=tid, connection_id=cid, template_name="document_approved_latest",
    )
    assert out["variables"] == ["name", "documentType"]
    assert calls["n"] == 1  # reused the cache; no second upstream call
