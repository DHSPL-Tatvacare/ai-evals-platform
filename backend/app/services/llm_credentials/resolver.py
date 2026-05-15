"""The single read path for LLM provider credentials.

resolve_llm_credentials(db, tenant_id, provider):
  enabled tenant row with a key -> decrypt, return ResolvedCredentials
  gemini + no key + tenant IS the system tenant -> env service-account path
  otherwise -> ProviderNotConfiguredError

No user_id. No auth_intent. No provider_override. Callers pass the provider
they already hold and get credentials only — the model name is the caller's
concern.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import SYSTEM_TENANT_ID
from app.models.tenant_llm_provider import TenantLlmProvider
from app.services.llm_credentials.crypto import decrypt_secret


class ProviderNotConfiguredError(RuntimeError):
    """Raised when a tenant has no usable credential for the requested provider.

    Carries a stable client-facing message — surface it as the HTTPException
    detail so the UI can show "configure <provider> in AI Settings".
    """

    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(
            f"LLM provider '{provider}' is not configured for this tenant. "
            f"An admin must enable it in AI Settings."
        )


@dataclass(frozen=True)
class ResolvedCredentials:
    provider: str
    api_key: str
    base_url: str | None
    extra_config: dict
    service_account_path: str | None


_CACHE: dict[tuple[str, str], tuple[float, ResolvedCredentials]] = {}
_CACHE_TTL_SECONDS = 60.0


def invalidate_cache(tenant_id: uuid.UUID | str, provider: str | None = None) -> None:
    """Drop cached credentials. Call after any admin write to a provider row."""
    tid = str(tenant_id)
    if provider is None:
        for key in [k for k in _CACHE if k[0] == tid]:
            _CACHE.pop(key, None)
    else:
        _CACHE.pop((tid, provider), None)


def _detect_system_sa_path() -> str:
    sa_path = settings.GEMINI_SERVICE_ACCOUNT_PATH
    return sa_path if (sa_path and os.path.isfile(sa_path)) else ""


async def resolve_llm_credentials(
    db: AsyncSession,
    tenant_id: uuid.UUID | str,
    provider: str,
) -> ResolvedCredentials:
    tid = uuid.UUID(str(tenant_id)) if not isinstance(tenant_id, uuid.UUID) else tenant_id
    cache_key = (str(tid), provider)
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    row = (
        await db.execute(
            select(TenantLlmProvider).where(
                TenantLlmProvider.tenant_id == tid,
                TenantLlmProvider.provider == provider,
                TenantLlmProvider.is_enabled.is_(True),
            )
        )
    ).scalar_one_or_none()

    resolved: ResolvedCredentials | None = None
    if row and row.api_key_encrypted:
        resolved = ResolvedCredentials(
            provider=provider,
            api_key=decrypt_secret(row.api_key_encrypted),
            base_url=row.base_url,
            extra_config=dict(row.extra_config or {}),
            service_account_path=None,
        )
    elif provider == "gemini" and tid == SYSTEM_TENANT_ID:
        sa_path = _detect_system_sa_path()
        if sa_path:
            resolved = ResolvedCredentials(
                provider="gemini",
                api_key="",
                base_url=None,
                extra_config={},
                service_account_path=sa_path,
            )

    if resolved is None:
        raise ProviderNotConfiguredError(provider)

    _CACHE[cache_key] = (now + _CACHE_TTL_SECONDS, resolved)
    return resolved
