"""Request-scoped bundle assembly (plan §4, §7).

:class:`BundleBuilder.build` composes:
- platform ontology (from :class:`PlatformOntology`, scoped to the request);
- per-pack projections (via ``pack.contribute_projection(scope)``);

into a single :class:`ScopedBundle`. The bundle is per-request ephemeral;
cache keying is deterministic so identical scope + versions hit the
cache.

Phase 1 is non-wiring: nothing calls ``build`` from the live turn loop.
M2 adds the single call site in ``chat_handler._execute_chat_turn``.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_engine.capability_pack import (
    CAPABILITY_PACK_REGISTRY,
    ensure_packs_registered,
)
from app.services.sherlock.bundle_types import (
    PackProjection,
    ScopedBundle,
    ScopeContext,
)
from app.services.sherlock.platform_ontology import PlatformOntology


_log = logging.getLogger(__name__)


# Cache-key type: tuple of hashables. Concrete values are:
# (tenant_id:str, effective_app_id:str, ontology_version:int,
#  frozenset of (pack_id, pack_version) tuples)
_CacheKey = tuple[Any, ...]


class BundleBuilder:
    """Assembles a :class:`ScopedBundle` from platform + pack inputs.

    Owns an in-process cache keyed by the tuple returned from
    :meth:`cache_key_for`. Cache bounds are deliberately modest — one
    entry per unique ``(tenant, app, ontology_version, pack_versions)``
    shape is enough for most workloads; tests use ``clear_cache()`` to
    reset between runs.
    """

    def __init__(self, db: AsyncSession, *, ontology: PlatformOntology | None = None):
        self._db = db
        self._ontology = ontology or PlatformOntology(db)
        self._cache: dict[_CacheKey, ScopedBundle] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def build(self, scope: ScopeContext) -> ScopedBundle:
        """Return a :class:`ScopedBundle` for the resolved scope.

        Deterministic: same scope + same ontology_version + same pack
        versions -> same bundle. Cache hit is a dict read.
        """
        ensure_packs_registered()

        pack_versions = self._frozen_pack_versions(scope.effective_pack_ids)
        view = await self._ontology.scoped(
            tenant_id=scope.tenant_id,
            app_id=scope.effective_app_id,
        )
        cache_key = self._compose_cache_key(scope, view.version, pack_versions)

        cached = self._cache.get(cache_key)
        if cached is not None and cached.scope == scope:
            return cached

        projections = tuple(
            self._collect_projection(pack_id, scope)
            for pack_id in scope.effective_pack_ids
        )
        projections = tuple(p for p in projections if p is not None)

        tool_specs = _merge_tool_specs(projections)
        tool_schema_enums = _merge_schema_enums(projections)
        question_hints = _merge_question_hints(projections)

        bundle = ScopedBundle(
            scope=scope,
            ontology_classes=view.classes,
            entity_types=view.entity_types,
            resolvers=view.resolvers,
            pack_projections=projections,
            tool_specs=tool_specs,
            tool_schema_enums=tool_schema_enums,
            question_hints=question_hints,
            cache_key=cache_key,
            ontology_version=view.version,
        )
        self._cache[cache_key] = bundle
        return bundle

    def clear_cache(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------------
    # Cache-key composition (callable without hitting the DB)
    # ------------------------------------------------------------------

    @staticmethod
    def _compose_cache_key(
        scope: ScopeContext,
        ontology_version: int,
        pack_versions: frozenset[tuple[str, str]],
    ) -> _CacheKey:
        return (
            str(scope.tenant_id),
            scope.effective_app_id,
            int(ontology_version),
            pack_versions,
        )

    @staticmethod
    def cache_key_for(
        scope: ScopeContext,
        ontology_version: int,
        pack_versions: Mapping[str, str],
    ) -> _CacheKey:
        """Build a cache key without running the builder — used by tests
        and by callers that want to pre-check cache membership.
        """
        frozen = frozenset(
            (str(pid), str(ver)) for pid, ver in (pack_versions or {}).items()
        )
        return BundleBuilder._compose_cache_key(scope, ontology_version, frozen)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _frozen_pack_versions(pack_ids: tuple[str, ...]) -> frozenset[tuple[str, str]]:
        out: set[tuple[str, str]] = set()
        for pid in pack_ids:
            pack = CAPABILITY_PACK_REGISTRY.get(pid)
            version = getattr(pack, 'pack_version', '0') if pack is not None else '0'
            out.add((pid, str(version)))
        return frozenset(out)

    @staticmethod
    def _collect_projection(pack_id: str, scope: ScopeContext) -> PackProjection | None:
        pack = CAPABILITY_PACK_REGISTRY.get(pack_id)
        if pack is None:
            _log.debug('BundleBuilder: pack %r not registered; skipping', pack_id)
            return None
        hook = getattr(pack, 'contribute_projection', None)
        if hook is None:
            # Default-empty projection (plan §7 backwards compatibility).
            return PackProjection(
                pack_id=pack_id,
                pack_version=str(getattr(pack, 'pack_version', '0')),
            )
        try:
            projection = hook(scope)
        except Exception:  # pragma: no cover - surfaced via tests when it fires
            _log.exception('pack %r contribute_projection raised', pack_id)
            return None
        if not isinstance(projection, PackProjection):
            _log.warning(
                'pack %r returned non-PackProjection from contribute_projection: %r',
                pack_id, type(projection).__name__,
            )
            return None
        return projection


# ---------------------------------------------------------------------------
# Deterministic merges
# ---------------------------------------------------------------------------


def _merge_tool_specs(
    projections: tuple[PackProjection, ...],
) -> tuple[Mapping[str, Any], ...]:
    seen: set[str] = set()
    merged: list[Mapping[str, Any]] = []
    # Iterate projections in stable pack_id order so repeated builds
    # produce identical tool ordering (prompt-cache hygiene, plan §8).
    for proj in sorted(projections, key=lambda p: p.pack_id):
        for spec in proj.tool_specs:
            name = spec.get('name') if isinstance(spec, Mapping) else None
            if not isinstance(name, str) or not name:
                continue
            if name in seen:
                continue
            seen.add(name)
            merged.append(dict(spec))
    return tuple(merged)


def _merge_schema_enums(
    projections: tuple[PackProjection, ...],
) -> Mapping[str, tuple[str, ...]]:
    buckets: dict[str, set[str]] = {}
    for proj in projections:
        for key, values in (proj.tool_schema_enums or {}).items():
            bucket = buckets.setdefault(str(key), set())
            for value in values:
                if isinstance(value, str) and value:
                    bucket.add(value)
    return {key: tuple(sorted(values)) for key, values in buckets.items()}


def _merge_question_hints(projections: tuple[PackProjection, ...]) -> str:
    chunks = [
        proj.question_hints for proj in projections
        if isinstance(proj.question_hints, str) and proj.question_hints.strip()
    ]
    return '\n\n'.join(chunks)


__all__ = ['BundleBuilder']
