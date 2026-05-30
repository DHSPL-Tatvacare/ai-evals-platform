"""Compaction thresholds for Sherlock v3 — single source of truth, shared FE/BE.

The supervisor owns a ``previous_response_id`` chain (``store=true``). The
Responses API's automatic ``context_management`` compaction only runs under
``store=false``, so it never fires for us; instead ``runtime`` explicitly calls
``responses.compact()`` on the supervisor chain once its rendered context
crosses ``CONTEXT_COMPACT_THRESHOLD_TOKENS``, then continues the chain from the
compacted response id.

The frontend reads ``CONTEXT_COMPACT_THRESHOLD_TOKENS`` and
``CONTEXT_PROGRESS_START_RATIO`` off the ``turn_finished`` payload — nothing
about thresholds is hardcoded on the FE. Change the constants here, both sides
move in lockstep.
"""
from __future__ import annotations

# Rendered-context size at which the supervisor chain is compacted, derived
# window-relative. The window is the supervisor model's context_limit from
# analytics.ref_llm_models_catalog (gpt-5.4 = 1_050_000); compaction fires at
# 90% of it. Static constant by design — no per-turn DB lookup.
MODEL_CONTEXT_WINDOW_TOKENS: int = 1_050_000
CONTEXT_COMPACT_RATIO: float = 0.9
CONTEXT_COMPACT_THRESHOLD_TOKENS: int = round(
    CONTEXT_COMPACT_RATIO * MODEL_CONTEXT_WINDOW_TOKENS
)

# Ratio above which the chat widget starts showing a "context filling" pill
# (75% → 0.75). Below this, no FE noise. Above, it ticks at 10% increments.
CONTEXT_PROGRESS_START_RATIO: float = 0.75
CONTEXT_PROGRESS_TICK_RATIO: float = 0.10


__all__ = [
    'MODEL_CONTEXT_WINDOW_TOKENS',
    'CONTEXT_COMPACT_RATIO',
    'CONTEXT_COMPACT_THRESHOLD_TOKENS',
    'CONTEXT_PROGRESS_START_RATIO',
    'CONTEXT_PROGRESS_TICK_RATIO',
]
