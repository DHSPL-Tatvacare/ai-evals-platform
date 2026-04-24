"""Typed provenance for scratchpad carry-forward (plan §8.1).

Phase 1 defines the enum and the wrapped-value shape so scope, bundle,
and pack projections can agree on how carried state gets tagged. The
chat-handler write-side integration happens in M2 — this module is
additive and import-only in Phase 1.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Provenance(str, Enum):
    """Where a filter / resolved-entity value came from.

    Carry-forward policy (plan §8.1):
    - ``user_explicit``    — sticky until user retracts (trust highest).
    - ``scope_derived``    — recomputed every turn; drops on scope change.
    - ``resolver_derived`` — sticky until user contradicts.
    - ``model_inferred``   — lowest trust; re-justify on reuse.
    - ``heuristic``        — opaque fallback; re-justify on reuse.
    """

    USER_EXPLICIT = 'user_explicit'
    SCOPE_DERIVED = 'scope_derived'
    RESOLVER_DERIVED = 'resolver_derived'
    MODEL_INFERRED = 'model_inferred'
    HEURISTIC = 'heuristic'


@dataclass(frozen=True)
class ProvenancedValue:
    """A value plus the provenance record that justifies its presence.

    Used by ``ScopeContext.scope_hints`` and (in M2) by scratchpad
    carry-forward writes. Frozen + slot-less dataclass so it is cheap to
    hash for cache-key composition and safe to share across threads.
    """

    value: Any
    provenance: Provenance
    confidence: float = 1.0
    source_turn_id: str | None = None
    source_tool: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'value': self.value,
            'provenance': self.provenance.value,
            'confidence': self.confidence,
            'source_turn_id': self.source_turn_id,
            'source_tool': self.source_tool,
        }
