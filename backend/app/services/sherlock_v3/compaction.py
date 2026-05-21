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

# Rendered-context size at which the supervisor chain is compacted.
# Production target: 120_000 (leaves ~50K headroom under gpt-5.4's working
# context). TEMP 2026-05-19: lowered to 20_000 for live UI verification of the
# compaction separator + progress pill. Revert to 120_000 after user sign-off.
CONTEXT_COMPACT_THRESHOLD_TOKENS: int = 20_000

# Ratio above which the chat widget starts showing a "context filling" pill
# (75% → 0.75). Below this, no FE noise. Above, it ticks at 10% increments.
CONTEXT_PROGRESS_START_RATIO: float = 0.75
CONTEXT_PROGRESS_TICK_RATIO: float = 0.10


__all__ = [
    'CONTEXT_COMPACT_THRESHOLD_TOKENS',
    'CONTEXT_PROGRESS_START_RATIO',
    'CONTEXT_PROGRESS_TICK_RATIO',
]
