"""Per-(tenant, app) resolved CRM surfaces, generated from the field map.

The resolved layer is the contract: a flat, named, fully-described view of the lead +
activity grains where every typed slot is renamed to its semantic key (``txt_01 AS condition``)
and consumers never touch ``raw_payload`` or a slot. Two faces, both projected from
``crm_field_map`` so they move in lockstep:

  * a **materialized view** ``analytics.dim_lead__<slug>`` / ``fact_lead_activity__<slug>`` for
    Sherlock/reporting (flat, indexed; refreshed on sync + on mapping publish), and
  * a **live view** for operational UI reads (zero staleness).

These are the one piece of per-tenant physical machinery (design §5 / DQ-6); their DDL varies
by tenant because the slot meaning does, so they are built at runtime from the map — Alembic
still owns every static table. There is no provider branch here: a new CRM is a new map.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import (
    CrmActivity,
    CrmActivityExt,
    CrmFieldMap,
    CrmLead,
    CrmLeadExt,
    SourceDatasetDefinition,
)
from app.services.orchestration.predicate_sql import compile_predicate

_PLUMBING = frozenset({"id", "tenant_id", "app_id", "crm_lead_id", "crm_activity_id"})


@dataclass(frozen=True)
class _GrainSpec:
    base: str            # resolved surface base name (the Sherlock-facing logical table)
    core: type
    ext: type
    core_table: str
    ext_table: str
    ext_fk: str
    indexed: tuple[str, ...]


_GRAINS: dict[str, _GrainSpec] = {
    "lead": _GrainSpec("dim_lead", CrmLead, CrmLeadExt, "crm_lead", "crm_lead_ext",
                       "crm_lead_id", ("lead_id", "lead_stage")),
    "activity": _GrainSpec("fact_lead_activity", CrmActivity, CrmActivityExt, "crm_activity",
                           "crm_activity_ext", "crm_activity_id", ("source_activity_id", "lead_id")),
}


def _slug(tenant_id: uuid.UUID, app_id: str) -> str:
    """Stable 12-hex digest of tenant+app — a safe, deterministic identifier suffix."""
    return hashlib.sha1(f"{tenant_id}:{app_id}".encode()).hexdigest()[:12]


def _quote_ident(name: str) -> str:
    """Quote a SQL identifier for raw-DDL interpolation (defense-in-depth for the alias)."""
    return '"' + name.replace('"', '""') + '"'


def resolved_matview_name(grain: str, tenant_id: uuid.UUID, app_id: str) -> str:
    return f"{_GRAINS[grain].base}__{_slug(tenant_id, app_id)}"


def resolved_live_view_name(grain: str, tenant_id: uuid.UUID, app_id: str) -> str:
    return f"{resolved_matview_name(grain, tenant_id, app_id)}_live"


def standard_columns(model: type) -> list[str]:
    """The model's semantic columns (everything except surrogate id / scope / FK plumbing)."""
    return [c for c in model.__table__.columns.keys() if c not in _PLUMBING]


def grain_models(grain: str) -> tuple[type, type, str]:
    """Public accessor for a grain's (core model, ext model, ext FK column)."""
    spec = _GRAINS[grain]
    return spec.core, spec.ext, spec.ext_fk


def resolved_projection(grain: str, bindings: list[CrmFieldMap]) -> list[tuple[str, str]]:
    """Ordered ``(sql_expr, output_alias)`` pairs: scope + standard passthrough + renamed slots.

    Standard columns project from the core alias ``l`` by their own name; each typed-slot binding
    renames its slot off the ext alias ``e`` to its semantic key. A binding whose slot is a core
    column is already covered by the standard tier and is skipped.
    """
    spec = _GRAINS[grain]
    ext_cols = {c for c in spec.ext.__table__.columns.keys() if c not in _PLUMBING}
    proj: list[tuple[str, str]] = [("l.tenant_id", "tenant_id"), ("l.app_id", "app_id")]
    proj += [(f"l.{c}", c) for c in standard_columns(spec.core)]
    for b in sorted(bindings, key=lambda b: b.slot):
        if b.slot in ext_cols:
            proj.append((f"e.{b.slot}", b.semantic_key))
    return proj


def _filter_columns(grain: str, bindings: list[CrmFieldMap]) -> dict[str, str]:
    """Resolved field name -> underlying column expression, so a filter binds to real columns only."""
    return {alias: expr for expr, alias in resolved_projection(grain, bindings)}


def _select_body(
    grain: str,
    tenant_id: uuid.UUID,
    app_id: str,
    bindings: list[CrmFieldMap],
    predicate: Any | None = None,
) -> str:
    spec = _GRAINS[grain]
    select = ", ".join(f"{expr} AS {_quote_ident(alias)}" for expr, alias in resolved_projection(grain, bindings))
    app_lit = app_id.replace("'", "''")
    where = f"l.tenant_id = '{tenant_id}'::uuid AND l.app_id = '{app_lit}'"
    if predicate is not None:
        where += " AND " + compile_predicate(predicate, _filter_columns(grain, bindings))
    return (
        f"SELECT {select} "
        f"FROM platform.{spec.core_table} l "
        f"LEFT JOIN platform.{spec.ext_table} e ON e.{spec.ext_fk} = l.id "
        f"WHERE {where}"
    )


def build_matview_ddl(
    grain: str, tenant_id: uuid.UUID, app_id: str, bindings: list[CrmFieldMap], predicate: Any | None = None
) -> str:
    name = resolved_matview_name(grain, tenant_id, app_id)
    return (
        f"CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.{name} AS "
        + _select_body(grain, tenant_id, app_id, bindings, predicate)
    )


def build_live_view_ddl(
    grain: str, tenant_id: uuid.UUID, app_id: str, bindings: list[CrmFieldMap], predicate: Any | None = None
) -> str:
    name = resolved_live_view_name(grain, tenant_id, app_id)
    return (
        f"CREATE OR REPLACE VIEW analytics.{name} AS "
        + _select_body(grain, tenant_id, app_id, bindings, predicate)
    )


async def _bindings_for(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str, connection_id: uuid.UUID, record_type: str
) -> list[CrmFieldMap]:
    rows = await db.execute(
        select(CrmFieldMap).where(
            CrmFieldMap.tenant_id == tenant_id,
            CrmFieldMap.app_id == app_id,
            CrmFieldMap.connection_id == connection_id,
            CrmFieldMap.record_type == record_type,
        )
    )
    return list(rows.scalars().all())


async def _active_filter_predicate(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str, connection_id: uuid.UUID, record_type: str
) -> Any | None:
    """Active dataset definition's filter for this grain, or None. Read-only, tenant+app scoped."""
    return (await db.execute(
        select(SourceDatasetDefinition.filter_predicate).where(
            SourceDatasetDefinition.tenant_id == tenant_id,
            SourceDatasetDefinition.app_id == app_id,
            SourceDatasetDefinition.connection_id == connection_id,
            SourceDatasetDefinition.record_type == record_type,
            SourceDatasetDefinition.status == "active",
        )
    )).scalar_one_or_none()


async def rebuild_resolved_surfaces(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str, connection_id: uuid.UUID
) -> list[str]:
    """(Re)build the matview + live view for every mapped grain; return the grains rebuilt.

    DROP-then-CREATE so a publish that changed the slot→column projection takes effect (a plain
    ``REFRESH`` can't change columns). The matview is created WITH DATA, so first build populates;
    later syncs call :func:`refresh_resolved_matviews`. Indexes are recreated each rebuild.
    """
    rebuilt: list[str] = []
    for grain, spec in _GRAINS.items():
        bindings = await _bindings_for(
            db, tenant_id=tenant_id, app_id=app_id, connection_id=connection_id, record_type=grain
        )
        if not bindings:
            continue
        predicate = await _active_filter_predicate(
            db, tenant_id=tenant_id, app_id=app_id, connection_id=connection_id, record_type=grain
        )
        mv = resolved_matview_name(grain, tenant_id, app_id)
        await db.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS analytics.{mv} CASCADE"))
        await db.execute(text(build_matview_ddl(grain, tenant_id, app_id, bindings, predicate)))
        await db.execute(text(build_live_view_ddl(grain, tenant_id, app_id, bindings, predicate)))
        for col in spec.indexed:
            await db.execute(text(
                f"CREATE INDEX IF NOT EXISTS ix_{mv}_{col} ON analytics.{mv} ({col})"
            ))
        rebuilt.append(grain)
    await db.flush()
    return rebuilt


async def refresh_resolved_matviews(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str, connection_id: uuid.UUID
) -> list[str]:
    """REFRESH the matview for each mapped grain (post-sync). Missing matview → rebuild it."""
    refreshed: list[str] = []
    for grain in _GRAINS:
        bindings = await _bindings_for(
            db, tenant_id=tenant_id, app_id=app_id, connection_id=connection_id, record_type=grain
        )
        if not bindings:
            continue
        mv = resolved_matview_name(grain, tenant_id, app_id)
        exists = (await db.execute(
            text("SELECT 1 FROM pg_matviews WHERE schemaname = 'analytics' AND matviewname = :n"),
            {"n": mv},
        )).scalar_one_or_none()
        if exists is None:
            await rebuild_resolved_surfaces(db, tenant_id=tenant_id, app_id=app_id, connection_id=connection_id)
            return list(_GRAINS)
        await db.execute(text(f"REFRESH MATERIALIZED VIEW analytics.{mv}"))
        refreshed.append(grain)
    await db.flush()
    return refreshed


async def matview_columns(db: AsyncSession, name: str) -> list[str]:
    """Live column names of an analytics matview, in ordinal order (empty if not built). Read-only."""
    rows = (await db.execute(
        text(
            "SELECT a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'analytics' AND c.relname = :n AND c.relkind = 'm' "
            "AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum"
        ),
        {"n": name},
    )).all()
    return [r[0] for r in rows]


async def resolved_sample(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str, grain: str, limit: int = 20
) -> tuple[list[str], list[dict[str, str | None]]]:
    """Read a small sample of the resolved matview (the 'what Sherlock sees' preview).

    Returns ``(columns, rows)`` with the resolved column names (scope columns hidden) and values
    stringified for display. Empty when no matview is built yet (no published map). Read-only.
    """
    mv = resolved_matview_name(grain, tenant_id, app_id)
    cols = [c for c in await matview_columns(db, mv) if c not in ("tenant_id", "app_id")]
    if not cols:
        return [], []
    select_list = ", ".join(cols)  # identifiers come from pg_catalog for our own matview — safe
    data = (await db.execute(
        text(f"SELECT {select_list} FROM analytics.{mv} LIMIT :lim"), {"lim": limit}
    )).all()
    rows = [{c: (None if v is None else str(v)) for c, v in zip(cols, r)} for r in data]
    return cols, rows


async def run_crm_resolved_populate(job_id, params: dict, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    """Job entry: rebuild (publish) or refresh (sync) the resolved surfaces for one connection."""
    from app.database import async_session

    app_id = str(params.get("app_id") or "").strip()
    connection_id = uuid.UUID(str(params["connection_id"]))
    mode = str(params.get("mode") or "refresh")

    async with async_session() as db:
        if mode == "rebuild":
            touched = await rebuild_resolved_surfaces(
                db, tenant_id=tenant_id, app_id=app_id, connection_id=connection_id
            )
        else:
            touched = await refresh_resolved_matviews(
                db, tenant_id=tenant_id, app_id=app_id, connection_id=connection_id
            )
        await db.commit()
    return {"mode": mode, "grains": touched}


__all__ = [
    "resolved_matview_name",
    "resolved_live_view_name",
    "resolved_projection",
    "build_matview_ddl",
    "build_live_view_ddl",
    "matview_columns",
    "rebuild_resolved_surfaces",
    "refresh_resolved_matviews",
    "resolved_sample",
    "run_crm_resolved_populate",
]
