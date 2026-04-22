"""Phase 3 — tools are derived from the ``CapabilityPack`` registry.

Prior to Phase 3 this module hand-maintained the ``CAPABILITY_TOOLS`` dict.
Post-phase, the registered packs own their ``tool_specs()``. The
harness-level entry point is ``resolve_tools(pack_ids, app_id)`` which:

1. Validates every pack id against ``CAPABILITY_PACK_REGISTRY`` (plan §Phase-3 step 6).
2. Concatenates pack ``tool_specs()`` in a deterministic order.
3. Runs each spec through ``fill_tool_description`` for the ``(pack, app_id)``
   so the §6.3.1 tokens resolve.
4. Memoizes on ``(frozenset(pack_ids), app_id)`` (plan §Phase-3 step 5).

The memoized list is returned by identity — callers MUST NOT mutate it in
place. ``_resolve_tools_for_app`` in ``chat_handler.py`` deep-copies
before injecting vocabulary enums to preserve the identity invariant.
"""
from __future__ import annotations

from typing import Any

from app.services.chat_engine.capability_pack import (
    CAPABILITY_PACK_REGISTRY,
    ensure_packs_registered,
    resolve_pack_ids_for_app,
)


# ---------------------------------------------------------------------------
# Memoized resolver
# ---------------------------------------------------------------------------


_RESOLVE_CACHE: dict[tuple[frozenset[str], str | None], list[dict[str, Any]]] = {}


def _resolve_tools_uncached(
    pack_ids: tuple[str, ...],
    app_id: str | None,
) -> list[dict[str, Any]]:
    """Concatenate pack specs, filling descriptions via each pack's own
    ``describe_tools(app_id)`` method.

    Plan §6.3 rule 3: every pack owns its own ``describe_tools()``. The
    main resolution path MUST route through it — Harness Core doesn't
    look up description strings directly. The generator's manifest-token
    substitution (``{{catalog_tables}}`` / ``{{surface_keys}}``) for
    property-level descriptions still runs, so the LLM sees the same
    per-app vocabulary on both the top-level and field-level strings.
    """

    from app.services.chat_engine.tool_description_generator import fill_tool_description

    ensure_packs_registered()
    tools: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pid in pack_ids:
        pack = CAPABILITY_PACK_REGISTRY.get(pid)
        if pack is None:
            raise RuntimeError(
                f"Unknown capability pack id {pid!r}. "
                f"Registered packs: {sorted(CAPABILITY_PACK_REGISTRY)}."
            )
        # Pack owns description rendering when an app_id is in scope.
        pack_descriptions: dict[str, str] = {}
        if app_id is not None:
            pack_descriptions = dict(pack.describe_tools(app_id))
        for spec in pack.tool_specs():
            name = spec.get('name')
            if not isinstance(name, str) or name in seen:
                continue
            if app_id is None:
                filled = dict(spec)
            else:
                # Run the generator to substitute property-level tokens
                # (e.g. ``{{surface_keys}}`` on get_surface_records.surface_key),
                # then overlay the pack-owned top-level description so the
                # pack's ``describe_tools`` is the single source of truth for
                # the description string.
                filled = fill_tool_description(dict(spec), app_id=app_id, pack=pack)
                pack_desc = pack_descriptions.get(name)
                if pack_desc is not None:
                    filled['description'] = pack_desc
            tools.append(filled)
            seen.add(name)
    return tools


def resolve_tools(
    pack_ids: list[str] | None = None,
    *,
    app_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return the resolved tool-spec list for the given pack ids.

    ``pack_ids`` is a list of ids that MUST exist in
    ``CAPABILITY_PACK_REGISTRY``. When ``None`` or empty, every
    registered pack contributes (deterministic order by pack id).

    Results are memoized by ``(frozenset(pack_ids), app_id)`` — the
    returned list is the same object across calls with identical
    arguments (plan §Phase-3 step 5, acceptance gate: "same object
    identity across 100 consecutive calls").
    """

    ensure_packs_registered()
    canonical_ids = resolve_pack_ids_for_app(pack_ids, app_id=app_id or '')
    key = (frozenset(canonical_ids), app_id)
    cached = _RESOLVE_CACHE.get(key)
    if cached is not None:
        return cached
    # Stable iteration order on cache miss — sort so two equal frozensets
    # produce identical lists regardless of caller-supplied order.
    resolved = _resolve_tools_uncached(tuple(sorted(canonical_ids)), app_id)
    _RESOLVE_CACHE[key] = resolved
    return resolved


def _clear_resolve_tools_cache_for_tests() -> None:
    """Test helper — the cache would otherwise persist across test cases."""

    _RESOLVE_CACHE.clear()
