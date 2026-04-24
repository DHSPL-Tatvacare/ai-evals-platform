"""Pack-agnostic read helpers over ``ScopedBundle``.

These helpers walk bundle-level generic fields (``safety_by_entity``,
``pack_projections[*].projected_classes[*].field_safety``) without any
SQL / vector / graph specificity. They belong here (not in a pack) so
any capability pack can consume the same view without reaching into a
sibling pack's module — the discipline the plan calls out in §364-380
(harness extension points generic; pack-specific code stays in the
owning pack).
"""
from __future__ import annotations

from app.services.sherlock.bundle_types import ScopedBundle


def explicit_only_column_set(bundle: ScopedBundle | None) -> set[str]:
    """Return the set of lower-cased column names marked ``explicit_only``.

    Sources, in precedence order:
    1. ``ClassProjection.field_safety`` — per-pack overrides pinned for a
       pack's storage. Most specific.
    2. ``bundle.safety_by_entity()`` — platform ontology + pack merged
       safety-by-entity-type. Entity names are treated as column names
       (matches the seed today where ``run_name`` is both an entity and
       a column).

    Missing bundle or no ``explicit_only`` marks → empty set. Callers
    that pass ``None`` (legacy / common-query cache) get a no-op result
    so downstream validators short-circuit cleanly.

    Pack-agnostic: a vector pack can consume this for its own safety
    validator the same way the analytics SQL validator does.
    """
    out: set[str] = set()
    if bundle is None:
        return out

    pack_projections = getattr(bundle, 'pack_projections', ())
    for proj in pack_projections or ():
        projected_classes = getattr(proj, 'projected_classes', ())
        for cls in projected_classes or ():
            field_safety = getattr(cls, 'field_safety', None) or {}
            for column, safety in field_safety.items():
                if str(safety).strip().lower() == 'explicit_only':
                    out.add(str(column).strip().lower())

    safety_by_entity = getattr(bundle, 'safety_by_entity', None)
    if callable(safety_by_entity):
        try:
            by_entity_raw = safety_by_entity() or {}
        except Exception:
            by_entity_raw = {}
        by_entity: dict[str, str] = dict(by_entity_raw) if isinstance(by_entity_raw, dict) else {}
        for entity, safety in by_entity.items():
            if str(safety).strip().lower() == 'explicit_only':
                out.add(str(entity).strip().lower())
    return out


__all__ = ['explicit_only_column_set']
