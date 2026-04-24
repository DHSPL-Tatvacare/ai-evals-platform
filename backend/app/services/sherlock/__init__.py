"""Sherlock assembly layer (Phase 1 / M1).

Phase 1 ships the upstream meaning layer that `_execute_chat_turn` will
consume in Phase 2 / M2:

- :mod:`app.services.sherlock.bundle_types` — dataclasses and enums.
- :mod:`app.services.sherlock.provenance` — typed provenance helpers.
- :mod:`app.services.sherlock.scope_guard` — deterministic scope gate.
- :mod:`app.services.sherlock.platform_ontology` — DB-backed ontology reader.
- :mod:`app.services.sherlock.bundle` — ``BundleBuilder``.

The module is intentionally free of runtime-loop coupling — no handler,
no route, no ``openai_agents_adapter`` edits land here. M2 wires the
bundle into the existing turn loop; this package is callable from a test
or a future orchestrator without dragging the harness along.
"""
from __future__ import annotations

from app.services.sherlock.bundle_types import (
    ClassProjection,
    EntityTypeRecord,
    OntologyClassRecord,
    PackProjection,
    ResolverRecord,
    ScopedBundle,
    ScopeContext,
    ScopeDenial,
)
from app.services.sherlock.provenance import Provenance, ProvenancedValue
from app.services.sherlock.scope_guard import ScopeGuard, scope_resolved_event
from app.services.sherlock.platform_ontology import (
    PLATFORM_ONTOLOGY_CLASSES,
    PlatformOntology,
    platform_ontology_version,
)
from app.services.sherlock.bundle import BundleBuilder
from app.services.sherlock.bundle_helpers import explicit_only_column_set
from app.services.sherlock.recognition import (
    RecognitionEvent,
    build_recognition_event,
    render_bundle_context,
)
from app.services.sherlock.turn_assembly import (
    TurnAssembly,
    bundle_resolvers_as_legacy,
    resolve_turn_scope_and_bundle,
)

__all__ = [
    'BundleBuilder',
    'ClassProjection',
    'EntityTypeRecord',
    'OntologyClassRecord',
    'PLATFORM_ONTOLOGY_CLASSES',
    'PackProjection',
    'PlatformOntology',
    'Provenance',
    'ProvenancedValue',
    'RecognitionEvent',
    'ResolverRecord',
    'ScopedBundle',
    'ScopeContext',
    'ScopeDenial',
    'ScopeGuard',
    'TurnAssembly',
    'build_recognition_event',
    'bundle_resolvers_as_legacy',
    'explicit_only_column_set',
    'platform_ontology_version',
    'render_bundle_context',
    'resolve_turn_scope_and_bundle',
    'scope_resolved_event',
]
