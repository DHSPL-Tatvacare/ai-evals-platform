"""Read-only test-connection probes per provider — return {ok, detail}, never raise."""
from __future__ import annotations

from typing import Any

import httpx


_TIMEOUT_SECONDS = 10.0


def _ok(detail: str) -> dict[str, Any]:
    return {"ok": True, "detail": detail}


def _fail(detail: str) -> dict[str, Any]:
    return {"ok": False, "detail": detail}


async def _probe_get(url: str, *, headers: dict[str, str]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers=headers)
        if 200 <= resp.status_code < 400:
            return _ok(f"HTTP {resp.status_code}")
        return _fail(f"HTTP {resp.status_code}: {resp.text[:160]}")
    except httpx.HTTPError as exc:
        return _fail(f"network error: {exc!r}")


async def probe_webhook(config: dict[str, Any]) -> dict[str, Any]:
    base = config.get("base_url", "").rstrip("/")
    header_name = str(config.get("auth_header_name", "")).strip()
    header_value = str(config.get("auth_header_value", "")).strip()
    headers = {header_name: header_value} if header_name and header_value else {}
    if not base:
        return _ok("saved generic webhook auth profile")
    return await _probe_get(base, headers=headers)


async def probe_wati(config: dict[str, Any]) -> dict[str, Any]:
    """A successful template listing proves the WATI creds reach the API."""
    from app.services.orchestration.adapters.wati import WatiAdapter

    try:
        templates = await WatiAdapter().list_message_templates(config)
        return _ok(f"{len(templates)} template(s) reachable")
    except Exception as exc:  # noqa: BLE001 — surface the vendor error verbatim
        return _fail(f"{exc}"[:200])


async def probe_bolna(config: dict[str, Any]) -> dict[str, Any]:
    """A successful agent listing proves the Bolna creds reach the API."""
    from app.services.orchestration.adapters.bolna import BolnaAdapter

    try:
        agents = await BolnaAdapter().list_agents(config)
        return _ok(f"{len(agents)} agent(s) reachable")
    except Exception as exc:  # noqa: BLE001 — surface the vendor error verbatim
        return _fail(f"{exc}"[:200])


async def probe_lsq(config: dict[str, Any]) -> dict[str, Any]:
    """A minimal Leads.Get (PageSize 1) proves the LSQ creds reach the API.

    Read-only: it reads at most one lead and never mutates. Auth is by
    ``accessKey`` + ``secretKey`` query params (LSQ has no token).
    """
    base = str(config.get("region_host", "")).rstrip("/")
    access_key = str(config.get("access_key", "")).strip()
    secret_key = str(config.get("secret_key", "")).strip()
    if not (base and access_key and secret_key):
        return _fail("missing region_host / access_key / secret_key")
    url = f"{base}/LeadManagement.svc/Leads.Get"
    params = {"accessKey": access_key, "secretKey": secret_key}
    body = {"Paging": {"PageIndex": 1, "PageSize": 1}}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, params=params, json=body)
        if 200 <= resp.status_code < 400:
            return _ok(f"HTTP {resp.status_code}")
        return _fail(f"HTTP {resp.status_code}: {resp.text[:160]}")
    except httpx.HTTPError as exc:
        return _fail(f"network error: {exc!r}")


_PROBES: dict[str, Any] = {
    "webhook": probe_webhook,
    "wati": probe_wati,
    "bolna": probe_bolna,
    "lsq": probe_lsq,
}


async def probe(provider: str, config: dict[str, Any]) -> dict[str, Any]:
    fn = _PROBES.get(provider)
    if fn is None:
        return _fail(f"unknown provider: {provider}")
    return await fn(config)
