"""CRM workspace PII masking (Phase 11E).

A "lead" in the CRM workspace is a real person — the list/detail rows the
``/inside-sales/leads`` and ``/calls`` surfaces return literally carry
prospects' names, phone numbers, emails, cities, and call notes. Not every
role with analytics access should see those raw values.

This module masks those PII field VALUES unless the caller's role is on the
allow-list in ``applications.config.crmWorkspace.piiVisibility`` (a closed
key set, invariant 18). The field NAMES are never hidden — only values.

Default-off: an app with no ``piiVisibility`` configured is treated as
"masking not set up yet" and rows pass through unmasked. Owner role
bypasses. Masking only takes effect once an operator declares the
visibility map.

NOTE: the serving layer still reads the CRM mirrors (the fact-backed
re-point is the remaining 11E step), so the PII field lists are enumerated
here from the mirror DTO shape — they mirror the manifest ``pii: true``
tags in §3.5 / §3.6 / §3.7.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.application import Application
from app.models.role import AccessRole
from app.schemas.app_config import AppConfig

# camelCase keys as they appear in the CRM workspace list/detail DTOs.
LEAD_PII_FIELDS: tuple[str, ...] = (
    "firstName",
    "lastName",
    "phone",
    "email",
    "city",
)
CALL_PII_FIELDS: tuple[str, ...] = (
    "phoneNumber",
    "displayNumber",
    "callNotes",
)

_MASK = "•••••••"


async def _pii_visibility_for_app(
    db: AsyncSession, app_id: str
) -> dict[str, list[str]]:
    """Load ``crmWorkspace.piiVisibility`` for an app. Empty dict if the
    app is missing or has no config (= masking not configured)."""
    app = await db.scalar(
        select(Application).where(Application.slug == app_id)
    )
    if app is None:
        return {}
    try:
        config = AppConfig.model_validate(app.config or {})
    except Exception:
        # A malformed app config must not break the serving path; treat
        # it as "no masking configured" and let the config validator
        # surface the real problem elsewhere.
        return {}
    return dict(config.crm_workspace.pii_visibility)


async def mask_crm_pii(
    rows: Sequence[dict[str, Any]],
    *,
    pii_fields: Iterable[str],
    auth: AuthContext,
    db: AsyncSession,
    app_id: str,
) -> list[dict[str, Any]]:
    """Mask PII field values in CRM workspace rows by the caller's role.

    A field is masked unless the caller holds a role listed for it in the
    app's ``piiVisibility`` map. No-op when ``piiVisibility`` is empty
    (masking not configured) or the caller is Owner. Returns new dicts;
    inputs are not mutated.
    """
    materialized = [dict(r) for r in rows]
    if auth.is_owner:
        return materialized

    pii_visibility = await _pii_visibility_for_app(db, app_id)
    if not pii_visibility:
        return materialized

    role = await db.get(AccessRole, auth.role_id)
    role_name = role.name if role is not None else None

    fields = tuple(pii_fields)
    for row in materialized:
        for field in fields:
            allowed = pii_visibility.get(field, [])
            if role_name in allowed:
                continue
            if row.get(field) not in (None, ""):
                row[field] = _MASK
    return materialized
