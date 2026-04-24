"""Bundle-derived recognition context (plan §4, §5.2).

M2 replaces the old pre-pass entity classifier. The outer agent no
longer runs an LLM call to label entities before the ReAct loop — app
aliases come from deterministic scope, entity safety flags come from
the platform ontology, and fuzzy identity resolution happens in-tool
via ``resolve_entity`` / ``lookup`` / ``get_surface_records``.

This module owns the two pieces the harness still needs:

1. :class:`RecognitionEvent` — stable shape for the ``entity_recognition``
   runtime event so existing consumers (UI + smoke tests) keep working.
   The shape mirrors the old ``EntityRecognitionResult`` but the values
   are synthesized from the deterministic bundle, not from a classifier.

2. :func:`render_bundle_context` — replaces the old
   ``render_entity_recognition_context``. Produces the per-turn prompt
   block that tells the outer agent which entity types are
   ``explicit_only`` (must go through the resolver tool), which app
   aliases are scope metadata (never a filter value), and which
   resolvers are available.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.services.sherlock.bundle_types import ScopedBundle, ScopeContext


class RecognitionEvent(BaseModel):
    """Backwards-compatible payload for the ``entity_recognition`` event.

    ``entities`` and ``needs_resolution`` stay in the shape the live UI
    already parses; M2 always emits an empty-entities in-scope payload
    because the LLM pre-pass is gone. ``out_of_scope_reason`` is
    populated only when ``ScopeGuard`` has already denied every
    candidate app (dead path in practice — the guard raises earlier —
    but kept for shape stability).
    """

    entities: list[dict[str, Any]] = Field(default_factory=list)
    is_platform_query: bool = True
    needs_resolution: bool = False
    out_of_scope_reason: str | None = None


def build_recognition_event(bundle: ScopedBundle) -> RecognitionEvent:
    """Synthesize the ``entity_recognition`` event payload from a bundle.

    Every live turn passes the scope gate by definition (``ScopeGuard``
    either resolves a single app or raises), so the synthesized event
    always reports ``is_platform_query=True``. Entity recognition itself
    now runs inside the ReAct loop via the resolver tools — there is no
    pre-pass classifier to populate ``entities`` / ``needs_resolution``.
    """
    del bundle  # reserved for future shape extension
    return RecognitionEvent()


def render_bundle_context(scope: ScopeContext, bundle: ScopedBundle) -> str:
    """Render the per-turn prompt block describing bundle-owned safety.

    Called by ``_execute_chat_turn`` after ``assemble_context`` and
    question-contract hints but before the pending-jobs block. The text
    is stable per scope/bundle — two turns with the same scope produce
    byte-identical output, which keeps the cache-prefix invariant in the
    per-turn zone.
    """
    lines: list[str] = []

    if scope.app_aliases:
        aliases = ', '.join(sorted(alias for alias in scope.app_aliases if alias))
        if aliases:
            lines.append(f'Current app aliases (scope metadata only): {aliases}.')
            lines.append(
                '- Treat these tokens as the active app scope, not as run_name / '
                'run_reference / evaluator / entity filter values.'
            )

    explicit_only = sorted({
        record.name
        for record in bundle.entity_types
        if record.safety == 'explicit_only' and record.name
    })
    if explicit_only:
        lines.append('Explicit-only entity types for this scope:')
        for name in explicit_only:
            lines.append(
                f'- {name}: call resolve_entity or lookup before using the '
                'value in data_query / get_surface_records.'
            )

    unsafe = sorted({
        record.name
        for record in bundle.entity_types
        if record.safety == 'unsafe' and record.name
    })
    if unsafe:
        lines.append('Blocked entity types for this scope:')
        for name in unsafe:
            lines.append(f'- {name}: not available in this app.')

    resolver_keys = sorted({
        record.key
        for record in bundle.resolvers
        if record.safety != 'unsafe' and record.key
    })
    if resolver_keys:
        lines.append(
            'Available resolvers (via resolve_entity / lookup): '
            + ', '.join(resolver_keys)
            + '.'
        )

    return '\n'.join(lines)


__all__ = [
    'RecognitionEvent',
    'build_recognition_event',
    'render_bundle_context',
]
