"""Live provider-listing service backing the builder inspector pickers.

Fetches WATI templates and Bolna agents from the vendor APIs and caches
results in-process for 30 seconds so a single inspector session does not
fan out upstream calls per keystroke.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_connection import ProviderConnection
from app.services.orchestration.connections import crypto


_CACHE_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class _CacheKey:
    connection_id: uuid.UUID
    bucket: str  # "bolna:agents" / "wati:templates"


@dataclass
class _CacheEntry:
    expires_at: float
    payload: list[dict[str, Any]]


_CACHE: dict[_CacheKey, _CacheEntry] = {}


def _cached(key: _CacheKey) -> Optional[list[dict[str, Any]]]:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    if entry.expires_at < time.monotonic():
        _CACHE.pop(key, None)
        return None
    return entry.payload


def _store(key: _CacheKey, payload: list[dict[str, Any]]) -> None:
    _CACHE[key] = _CacheEntry(
        expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
        payload=payload,
    )


def _bust(key: _CacheKey) -> None:
    _CACHE.pop(key, None)


async def _load_connection(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    connection_id: uuid.UUID,
    expected_provider: str,
) -> Optional[dict[str, Any]]:
    """Tenant + app-scoped connection load; returns plaintext config or None."""
    row = await db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id,
            ProviderConnection.tenant_id == tenant_id,
            ProviderConnection.app_id == app_id,
            ProviderConnection.active.is_(True),
            ProviderConnection.provider == expected_provider,
        )
    )
    if row is None:
        return None
    return crypto.decrypt(row.config_encrypted)


async def list_connection_bolna_agents(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    connection_id: uuid.UUID,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return {provider, items, error}. Soft-error: HTTP stays 200 on upstream failure."""
    key = _CacheKey(connection_id=connection_id, bucket="bolna:agents")
    if refresh:
        _bust(key)
    cached = _cached(key)
    if cached is not None:
        return {"provider": "bolna", "items": cached, "error": None}

    config = await _load_connection(
        db,
        tenant_id=tenant_id,
        app_id=app_id,
        connection_id=connection_id,
        expected_provider="bolna",
    )
    if config is None:
        return {
            "provider": "bolna",
            "items": [],
            "error": "Connection not found, archived, or not a Bolna connection.",
        }

    from app.services.orchestration.adapters.bolna import BolnaAdapter, BolnaServiceError

    adapter = BolnaAdapter()
    try:
        items = await adapter.list_agents(config)
    except BolnaServiceError as exc:
        return {"provider": "bolna", "items": [], "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — soft error contract
        return {"provider": "bolna", "items": [], "error": f"Bolna upstream error: {exc.__class__.__name__}"}

    _store(key, items)
    return {"provider": "bolna", "items": items, "error": None}


async def list_connection_wati_templates(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    connection_id: uuid.UUID,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return {provider, items, error}. Soft-error: HTTP stays 200 on upstream failure."""
    key = _CacheKey(connection_id=connection_id, bucket="wati:templates")
    if refresh:
        _bust(key)
    cached = _cached(key)
    if cached is not None:
        return {"provider": "wati", "items": cached, "error": None}

    config = await _load_connection(
        db,
        tenant_id=tenant_id,
        app_id=app_id,
        connection_id=connection_id,
        expected_provider="wati",
    )
    if config is None:
        return {
            "provider": "wati",
            "items": [],
            "error": "Connection not found, archived, or not a WATI connection.",
        }

    from app.services.orchestration.adapters.wati import WatiAdapter, WatiServiceError

    adapter = WatiAdapter()
    try:
        items = await adapter.list_message_templates(config)
    except WatiServiceError as exc:
        return {"provider": "wati", "items": [], "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — soft error contract
        return {"provider": "wati", "items": [], "error": f"WATI upstream error: {exc.__class__.__name__}"}

    _store(key, items)
    return {"provider": "wati", "items": items, "error": None}


async def get_agent_variables(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
    agent_id: Optional[str] = None,
    template_name: Optional[str] = None,
) -> dict[str, Any]:
    """Return variables for a Bolna agent or WATI template. Soft-error envelope."""
    row = await db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id,
            ProviderConnection.tenant_id == tenant_id,
        )
    )
    if row is None:
        return {"provider": "unknown", "variables": [], "error": "Connection not found."}

    provider = row.provider
    config = crypto.decrypt(row.config_encrypted)

    if provider == "bolna" and agent_id:
        from app.services.orchestration.adapters.bolna import BolnaAdapter, BolnaServiceError
        adapter = BolnaAdapter()
        try:
            agent = await adapter.get_agent(config, agent_id=agent_id)
        except (BolnaServiceError, Exception) as exc:  # noqa: BLE001
            return {"provider": "bolna", "variables": [], "error": str(exc)}
        agent_cfg = agent.get("agent_config") or {}
        variables = agent_cfg.get("variables") or []
        if isinstance(variables, list):
            variables = [str(v) for v in variables if v]
        else:
            variables = []
        return {"provider": "bolna", "variables": variables, "error": None}

    if provider == "wati" and template_name:
        from app.services.orchestration.adapters.wati import WatiAdapter, WatiServiceError
        adapter = WatiAdapter()
        try:
            templates = await adapter.list_message_templates(config)
        except (WatiServiceError, Exception) as exc:  # noqa: BLE001
            return {"provider": "wati", "variables": [], "error": str(exc)}
        match = next((t for t in templates if t["name"] == template_name), None)
        if match is None:
            return {"provider": "wati", "variables": [], "error": f"Template {template_name!r} not found."}
        return {"provider": "wati", "variables": match.get("parameters") or [], "error": None}

    return {"provider": provider, "variables": [], "error": None}
