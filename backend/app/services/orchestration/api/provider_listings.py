"""Live provider-listing service backing the builder inspector pickers.

Fetches WATI templates and Bolna agents from the vendor APIs and caches
results in-process. Approved templates change rarely, so the passive TTL is
long and the explicit Refresh button is the manual invalidation path. A
per-key single-flight lock coalesces the concurrent fetches one inspector-open
fires (template picker + variable-mapping introspection) into one upstream call.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_connection import ProviderConnection
from app.services.orchestration.adapters import VariableSurface
from app.services.orchestration.connections import crypto
from app.services.orchestration.connections.scope import connection_app_scope_clause


# Approved provider templates/agents are near-static — refresh is operator-driven,
# not time-driven. Long passive TTL; the Refresh button forces a live fetch.
_CACHE_TTL_SECONDS = 604800.0  # 7 days


@dataclass(frozen=True)
class _CacheKey:
    connection_id: uuid.UUID
    bucket: str  # "bolna:agents" / "wati:templates"


@dataclass
class _CacheEntry:
    expires_at: float
    payload: list[dict[str, Any]]


_CACHE: dict[_CacheKey, _CacheEntry] = {}
# Per-key single-flight: concurrent inspector-open fetches share one upstream call.
_LOCKS: dict[_CacheKey, asyncio.Lock] = {}


def _lock_for(key: _CacheKey) -> asyncio.Lock:
    lock = _LOCKS.get(key)
    if lock is None:
        lock = _LOCKS.setdefault(key, asyncio.Lock())
    return lock


def _cached(key: _CacheKey) -> Optional[list[dict[str, Any]]]:
    """Fresh (within TTL) payload, or None. Expired entries linger so
    ``_last_good`` can still serve them when the upstream is rate-limiting."""
    entry = _CACHE.get(key)
    if entry is None or entry.expires_at < time.monotonic():
        return None
    return entry.payload


def _last_good(key: _CacheKey) -> Optional[list[dict[str, Any]]]:
    """Last successfully fetched payload regardless of TTL — graceful-degrade source."""
    entry = _CACHE.get(key)
    return entry.payload if entry else None


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
            connection_app_scope_clause(app_id),
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


def _friendly_wati_error(exc: Exception) -> str:
    """Operator-facing copy. Rate limits are transient and self-resolve."""
    text = str(exc)
    if "429" in text or "rate limit" in text.lower():
        return "WhatsApp provider is rate-limiting template lookups — try Refresh again in a minute."
    return "Couldn't load WhatsApp templates from the provider. Try Refresh."


async def _fetch_wati_templates_cached(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    connection_id: uuid.UUID,
    refresh: bool = False,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Single source for WATI templates — both the picker and variable-mapping
    introspection call this so an inspector-open fans out one upstream call, not two.

    Single-flight per connection; long TTL; on upstream failure (e.g. 429) falls
    back to the last-known-good list instead of blanking the picker.
    """
    key = _CacheKey(connection_id=connection_id, bucket="wati:templates")
    if not refresh:
        fresh = _cached(key)
        if fresh is not None:
            return fresh, None

    async with _lock_for(key):
        # Re-check inside the lock: a concurrent caller may have just populated it.
        if not refresh:
            fresh = _cached(key)
            if fresh is not None:
                return fresh, None

        config = await _load_connection(
            db,
            tenant_id=tenant_id,
            app_id=app_id,
            connection_id=connection_id,
            expected_provider="wati",
        )
        if config is None:
            return [], "Connection not found, archived, or not a WATI connection."

        from app.services.orchestration.adapters.wati import WatiAdapter, WatiServiceError

        try:
            items = await WatiAdapter().list_message_templates(config)
        except (WatiServiceError, Exception) as exc:  # noqa: BLE001 — soft error contract
            stale = _last_good(key)
            if stale is not None:
                # Don't punish a transient rate limit by emptying the picker.
                return stale, _friendly_wati_error(exc)
            return [], _friendly_wati_error(exc)

        _store(key, items)
        return items, None


async def list_connection_wati_templates(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    connection_id: uuid.UUID,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return {provider, items, error}. Soft-error: HTTP stays 200 on upstream failure."""
    items, error = await _fetch_wati_templates_cached(
        db, tenant_id=tenant_id, app_id=app_id,
        connection_id=connection_id, refresh=refresh,
    )
    return {"provider": "wati", "items": items, "error": error}


async def list_connection_phone_numbers(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    connection_id: uuid.UUID,
    provider: str,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return {provider, items, error}. Soft-error: HTTP stays 200 on upstream failure."""
    bucket = f"{provider}:phones"
    key = _CacheKey(connection_id=connection_id, bucket=bucket)
    if refresh:
        _bust(key)
    cached = _cached(key)
    if cached is not None:
        return {"provider": provider, "items": cached, "error": None}

    config = await _load_connection(
        db,
        tenant_id=tenant_id,
        app_id=app_id,
        connection_id=connection_id,
        expected_provider=provider,
    )
    if config is None:
        return {
            "provider": provider,
            "items": [],
            "error": f"Connection not found, archived, or not a {provider} connection.",
        }

    if provider == "bolna":
        from app.services.orchestration.adapters.bolna import BolnaAdapter, BolnaServiceError
        adapter: Any = BolnaAdapter()
        error_class: Any = BolnaServiceError
    elif provider == "wati":
        from app.services.orchestration.adapters.wati import WatiAdapter, WatiServiceError
        adapter = WatiAdapter()
        error_class = WatiServiceError
    else:
        return {"provider": provider, "items": [], "error": f"Provider {provider!r} does not support phone-number listing."}

    try:
        items = await adapter.list_phone_numbers(config)
    except error_class as exc:
        return {"provider": provider, "items": [], "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — soft error contract
        return {"provider": provider, "items": [], "error": f"{provider} upstream error: {exc.__class__.__name__}"}

    _store(key, items)
    return {"provider": provider, "items": items, "error": None}


def _surface_response(
    provider: str, surface: VariableSurface, *, error: Optional[str] = None,
) -> dict[str, Any]:
    """One cross-provider response shape, built from a VariableSurface."""
    return {
        "provider": provider,
        "variables": surface.variables,
        "prompt": surface.prompt,
        "welcome_message": surface.welcome_message,
        "body": surface.body,
        "body_original": surface.body_original,
        "error": error,
    }


async def get_agent_variables(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
    agent_id: Optional[str] = None,
    template_name: Optional[str] = None,
) -> dict[str, Any]:
    """Return the variable surface for a Bolna agent or WATI template. Soft-error envelope."""
    row = await db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id,
            ProviderConnection.tenant_id == tenant_id,
        )
    )
    if row is None:
        return _surface_response("unknown", VariableSurface(), error="Connection not found.")

    provider = row.provider
    config = crypto.decrypt(row.config_encrypted)

    if provider == "bolna" and agent_id:
        from app.services.orchestration.adapters.bolna import (
            BolnaAdapter,
            BolnaServiceError,
            extract_variables,
        )
        adapter = BolnaAdapter()
        try:
            agent = await adapter.get_agent(config, agent_id=agent_id)
        except (BolnaServiceError, Exception) as exc:  # noqa: BLE001
            return _surface_response("bolna", VariableSurface(), error=str(exc))
        return _surface_response("bolna", extract_variables(agent))

    if provider == "wati" and template_name:
        # Shares the picker's cache + single-flight — one upstream fetch per
        # inspector-open, not two. No direct adapter call (that was the
        # parallel, uncached path that helped trip the WATI 429).
        templates, error = await _fetch_wati_templates_cached(
            db, tenant_id=tenant_id, app_id=row.app_id, connection_id=connection_id,
        )
        if error and not templates:
            return _surface_response("wati", VariableSurface(), error=error)
        match = next((t for t in templates if t["name"] == template_name), None)
        if match is None:
            return _surface_response(
                "wati", VariableSurface(), error=f"Template {template_name!r} not found.",
            )
        return _surface_response("wati", VariableSurface(
            variables=match.get("parameters") or [],
            body=match.get("body") or "",
            body_original=match.get("body_original"),
        ))

    return _surface_response(provider, VariableSurface())
