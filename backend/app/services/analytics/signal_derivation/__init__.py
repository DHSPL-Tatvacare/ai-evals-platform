"""Signal derivation framework (Phase 11A).

Generic, strategy-based derivation of ``analytics.fact_lead_signal`` rows
from normalized fact/dim surfaces. Strategy plugins are code; signal
definitions are tenant business config in ``analytics.signal_definition``.

See docs/plans/2026-05-12-analytics-facts-canonical-manifest-thinning.md §7.4.
"""
from __future__ import annotations

from app.services.analytics.signal_derivation.base import (
    DerivedSignal,
    SignalStrategy,
    SignalStrategyError,
    StrategyContext,
)
from app.services.analytics.signal_derivation.registry import (
    get_strategy,
    register_strategy,
    registered_strategies,
)

__all__ = [
    "DerivedSignal",
    "SignalStrategy",
    "SignalStrategyError",
    "StrategyContext",
    "get_strategy",
    "register_strategy",
    "registered_strategies",
]
