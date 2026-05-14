"""Signal derivation framework — the Transform-pass orchestrator.

Phase 11A of docs/plans/2026-05-12-analytics-facts-canonical-manifest-thinning.md.

``run_signal_derivation`` is the shared core: load every enabled
``signal_definition``, resolve its strategy plugin, load rows from the
declared normalized source surface, derive signals, and upsert them into
``analytics.fact_lead_signal`` keyed on ``uq_fact_lead_signal_framework``.

The scheduled ``derive-signals`` job calls this with no scope (all
tenants / apps — the "T" of ELT). It is idempotent: re-running upserts in
place, so a pass over unchanged lead state collapses to one row per
``(lead, signal_type, detected_at)``.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics_lead_facts import DimLead, FactLeadSignal
from app.models.analytics_log import LogFactPopulationRun
from app.models.analytics_signal_definition import SignalDefinition
from app.services.analytics.signal_derivation.base import (
    DerivedSignal,
    StrategyContext,
)
from app.services.analytics.signal_derivation.registry import get_strategy

_log = logging.getLogger(__name__)

JOB_TYPE = "derive-signals"
_BATCH_SIZE = 1000

# Conflict target for framework-written rows — matches the partial unique
# index ``uq_fact_lead_signal_framework`` (migration 0044).
_FRAMEWORK_KEY = ["tenant_id", "app_id", "lead_id", "signal_type", "detected_at"]
_FRAMEWORK_KEY_WHERE = text("signal_definition_id IS NOT NULL")


# ── Source-surface loaders ─────────────────────────────────────────────
# A signal definition reads ONE normalized surface. Each loader yields
# batches of plain-dict rows for one ``(tenant_id, app_id)``. Strategies
# resolve their ``field`` paths against these dicts. Phase 11B adds
# fact_lead_activity / eval-thread loaders for the LLM strategies.

def _orm_row_to_dict(obj: Any) -> dict[str, Any]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


async def _load_dim_lead_batches(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str
) -> AsyncIterator[list[dict[str, Any]]]:
    """Keyset-paginate ``analytics.dim_lead`` by ``lead_id``."""
    cursor: str | None = None
    while True:
        stmt = (
            select(DimLead)
            .where(DimLead.tenant_id == tenant_id, DimLead.app_id == app_id)
            .order_by(DimLead.lead_id)
            .limit(_BATCH_SIZE)
        )
        if cursor is not None:
            stmt = stmt.where(DimLead.lead_id > cursor)
        rows = (await db.execute(stmt)).scalars().all()
        if not rows:
            return
        yield [_orm_row_to_dict(r) for r in rows]
        if len(rows) < _BATCH_SIZE:
            return
        cursor = rows[-1].lead_id


_SOURCE_LOADERS = {
    "dim_lead": _load_dim_lead_batches,
}


# ── Upsert ─────────────────────────────────────────────────────────────

def _fact_row(
    signal: DerivedSignal, *, tenant_id: uuid.UUID, app_id: str, definition_id: uuid.UUID
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "app_id": app_id,
        "signal_definition_id": definition_id,
        "lead_id": signal.lead_id,
        "signal_type": signal.signal_type,
        "signal_value": signal.signal_value,
        "signal_value_numeric": signal.signal_value_numeric,
        "detected_at": signal.detected_at,
        "attributes": signal.attributes,
        "ordinal": 0,
    }


async def _upsert_signals(
    db: AsyncSession,
    rows: list[dict[str, Any]],
) -> int:
    """Upsert framework signal rows. Returns the row count touched."""
    if not rows:
        return 0
    stmt = pg_insert(FactLeadSignal).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=_FRAMEWORK_KEY,
        index_where=_FRAMEWORK_KEY_WHERE,
        set_={
            "signal_definition_id": stmt.excluded.signal_definition_id,
            "signal_value": stmt.excluded.signal_value,
            "signal_value_numeric": stmt.excluded.signal_value_numeric,
            "attributes": stmt.excluded.attributes,
        },
    )
    await db.execute(stmt)
    return len(rows)


# ── Orchestrator ───────────────────────────────────────────────────────

async def _run_one_definition(
    db: AsyncSession, definition: SignalDefinition
) -> dict[str, Any]:
    """Derive + upsert every signal for one definition. Commits per batch."""
    strategy = get_strategy(definition.strategy)
    strategy.validate(definition.definition)

    loader = _SOURCE_LOADERS.get(definition.source_surface)
    if loader is None:
        raise ValueError(
            f"signal_definition {definition.id}: no loader for source_surface "
            f"{definition.source_surface!r} (known: {sorted(_SOURCE_LOADERS)})"
        )

    ctx = StrategyContext(
        tenant_id=definition.tenant_id, app_id=definition.app_id
    )
    rows_written = 0
    leads_seen = 0
    async for batch in loader(
        db, tenant_id=definition.tenant_id, app_id=definition.app_id
    ):
        leads_seen += len(batch)
        derived = await strategy.derive(
            definition=definition.definition, source_rows=batch, ctx=ctx
        )
        fact_rows = [
            _fact_row(
                d,
                tenant_id=definition.tenant_id,
                app_id=definition.app_id,
                definition_id=definition.id,
            )
            for d in derived
        ]
        rows_written += await _upsert_signals(db, fact_rows)
        await db.commit()

    return {
        "signal_definition_id": str(definition.id),
        "signal_set": definition.signal_set,
        "strategy": definition.strategy,
        "leads_seen": leads_seen,
        "rows_written": rows_written,
    }


async def run_signal_derivation(
    db: AsyncSession,
    *,
    scope_tenant_id: uuid.UUID | None = None,
    scope_app_id: str | None = None,
) -> dict[str, Any]:
    """Run the signal-derivation Transform across enabled definitions.

    No scope → all tenants / apps (the scheduled platform pass). Scope
    args narrow it (used by tests and, later, the one-shot path).
    """
    stmt = select(SignalDefinition).where(SignalDefinition.enabled.is_(True))
    if scope_tenant_id is not None:
        stmt = stmt.where(SignalDefinition.tenant_id == scope_tenant_id)
    if scope_app_id is not None:
        stmt = stmt.where(SignalDefinition.app_id == scope_app_id)
    definitions = (await db.execute(stmt)).scalars().all()

    per_definition: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for definition in definitions:
        try:
            per_definition.append(await _run_one_definition(db, definition))
        except Exception as exc:  # noqa: BLE001 — one bad definition must not
            # sink the whole pass; record it and move on.
            await db.rollback()
            _log.exception(
                "signal_derivation.definition_failed id=%s set=%s",
                definition.id,
                definition.signal_set,
            )
            errors.append(
                {"signal_definition_id": str(definition.id), "error": str(exc)}
            )

    summary: dict[str, Any] = {
        "definitions_run": len(per_definition),
        "definitions_failed": len(errors),
        "rows_written": sum(d["rows_written"] for d in per_definition),
        "per_definition": per_definition,
        "errors": errors,
    }

    # One audit breadcrumb per pass. Tenant/app are the run's scope or the
    # system tenant for the unscoped platform pass.
    from app.constants import SYSTEM_TENANT_ID

    db.add(
        LogFactPopulationRun(
            tenant_id=scope_tenant_id or SYSTEM_TENANT_ID,
            app_id=scope_app_id or "",
            job_type=JOB_TYPE,
            status="error" if errors else "completed",
            metadata_=summary,
        )
    )
    await db.commit()
    return summary
