"""Signal derivation framework — strategy interface + shared types.

Phase 11A of docs/plans/2026-05-12-analytics-facts-canonical-manifest-thinning.md.

A *strategy* is generic code; a *definition* (``analytics.signal_definition``)
is tenant business config. Each strategy plugin turns a definition + rows
from a normalized source surface into ``DerivedSignal`` objects; the
``derive-signals`` Transform job stamps them into ``analytics.fact_lead_signal``.

Strategies read ONLY normalized fact/dim surfaces — never ``raw_payload``,
never a mirror (invariant 21). The strategy never touches the DB or the
manifest directly; the orchestrator owns I/O.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class DerivedSignal:
    """One derived signal about one lead — the strategy's unit of output.

    The orchestrator maps each to a ``FactLeadSignal`` row, stamping
    ``tenant_id`` / ``app_id`` / ``signal_definition_id``. The framework
    dedup key is ``(tenant_id, app_id, lead_id, signal_type, detected_at)``;
    ``detected_at`` is source-state-derived so a re-run over unchanged
    state collapses to one row.
    """

    lead_id: str
    signal_type: str
    detected_at: datetime
    signal_value: str | None = None
    signal_value_numeric: Decimal | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyContext:
    """Ambient context the orchestrator hands a strategy.

    ``rule`` ignores everything but the scoping ids. The LLM strategies
    (Phase 11B) reach for ``llm_provider``. No DB session is exposed —
    the orchestrator loads source rows and persists output; strategies
    stay pure-ish (rule is fully pure; LLM strategies do provider I/O only).
    """

    tenant_id: uuid.UUID
    app_id: str
    llm_provider: Any | None = None


class SignalStrategyError(ValueError):
    """Raised when a definition body is structurally invalid for a strategy."""


class SignalStrategy(ABC):
    """Base class for the three strategy plugins (``rule`` / ``llm_profile``
    / ``llm_transcript``). Registered by ``key`` in the registry."""

    #: Strategy key — must match ``signal_definition.strategy``.
    key: str

    @abstractmethod
    def validate(self, definition: Mapping[str, Any]) -> None:
        """Raise ``SignalStrategyError`` if the definition body is invalid.

        Run at definition write time (admin screen) and at boot before the
        first Transform pass — fail loud, never silently skip.
        """

    @abstractmethod
    def attribute_schemas(
        self, definition: Mapping[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Return ``{signal_type: {jsonb_key: AttributeKeySchema-shaped dict}}``.

        The manifest projection composes ``fact_lead_signal.attribute_schemas``
        from every enabled definition's output here (invariant 21, §7.4).
        A signal_type with no JSONB keys returns an empty dict.
        """

    @abstractmethod
    async def derive(
        self,
        *,
        definition: Mapping[str, Any],
        source_rows: Sequence[Mapping[str, Any]],
        ctx: StrategyContext,
    ) -> list[DerivedSignal]:
        """Produce derived signals from rows of the normalized source surface.

        ``source_rows`` are mappings of the ``source_surface`` table
        (e.g. ``dim_lead``) for one ``(tenant, app)`` batch. Pure for
        ``rule``; the LLM strategies do provider I/O via ``ctx``.
        """
