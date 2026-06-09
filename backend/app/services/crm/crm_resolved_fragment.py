"""Per-tenant resolved manifest fragment — projected from the field map, composed at session.

Tier 2 of the two-tier manifest (DQ-10). The static app catalog/manifest (Tier 1) is boot-validated
and never carries per-tenant slot meaning. This module projects ``crm_field_map`` into a fragment
(the per-tenant resolved columns + the matview's physical name + resolved exemplars) and composes it
onto the static workbench catalog **for one turn** — so Sherlock sees ``condition``, never ``txt_01``
or ``raw_payload``. Same input (the map), same trigger as the matview: lockstep by construction.

The fragment is derived live at session-compute; boot validation never sees a per-tenant object.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmFieldMap
from app.services.crm.crm_resolved_populator import (
    grain_models,
    matview_columns,
    resolved_matview_name,
    standard_columns,
)

# logical catalog table (Sherlock-facing) per grain — the static catalog keys we overlay onto.
_LOGICAL_TABLE = {"lead": "dim_lead", "activity": "fact_lead_activity"}
_GRAIN_KEY = {"lead": "lead_id", "activity": "source_activity_id"}

# the workbench DataType subset the resolved layer emits (slots are typed, never geo).
ResolvedDataType = Literal["nominal", "quantitative", "temporal", "boolean"]


@dataclass(frozen=True)
class FragmentColumn:
    name: str
    data_type: ResolvedDataType
    is_enum: bool = False
    sample_values: tuple = ()
    synonyms: tuple = ()


@dataclass(frozen=True)
class FragmentGrain:
    logical_table: str                   # 'dim_lead' | 'fact_lead_activity'
    matview_table: str                   # 'dim_lead__<slug>'
    grain_key: str
    columns: tuple[FragmentColumn, ...]


@dataclass(frozen=True)
class CrmResolvedFragment:
    app_id: str
    version: int
    grains: tuple[FragmentGrain, ...] = field(default_factory=tuple)
    exemplars: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # (name, sql)


def _classify_orm(col_type) -> ResolvedDataType:
    if isinstance(col_type, Boolean):
        return "boolean"
    if isinstance(col_type, (Integer, Numeric)):
        return "quantitative"
    if isinstance(col_type, DateTime):
        return "temporal"
    return "nominal"  # String / Text / fallback


def _classify_binding(data_type: str) -> ResolvedDataType | None:
    dt = (data_type or "text").lower()
    if dt in ("int", "integer", "bigint", "num", "numeric", "number", "decimal", "float"):
        return "quantitative"
    if dt in ("dt", "datetime", "date", "timestamp"):
        return "temporal"
    if dt in ("bool", "boolean"):
        return "boolean"
    if dt in ("json", "jsonb"):
        return None  # nested JSONB is never exposed as a flat logical column
    return "nominal"


def _grain_columns(grain: str, bindings: list[CrmFieldMap]) -> list[FragmentColumn]:
    core_model, ext_model, ext_fk = grain_models(grain)
    core_types = {c: core_model.__table__.columns[c].type for c in standard_columns(core_model)}
    ext_cols = {c for c in ext_model.__table__.columns.keys()
                if c not in {"id", "tenant_id", "app_id", ext_fk}}
    out: list[FragmentColumn] = [
        FragmentColumn(name=c, data_type=_classify_orm(t)) for c, t in core_types.items()
    ]
    for b in sorted(bindings, key=lambda b: b.slot):
        if b.slot not in ext_cols:
            continue  # standard-column binding already covered by the core tier
        dtype = _classify_binding(b.data_type)
        if dtype is None:
            continue
        values = tuple(sorted({str(v) for v in (b.value_map or {}).values()}))
        out.append(FragmentColumn(
            name=b.semantic_key, data_type=dtype,
            is_enum=bool(values), sample_values=values,
        ))
    return out


def _exemplar_sql(matview: str, cols: list[FragmentColumn], grain_key: str) -> str:
    picks = [grain_key] + [c.name for c in cols if c.name not in (grain_key, "tenant_id", "app_id")][:3]
    select_list = ", ".join(dict.fromkeys(picks))
    return (
        f"SELECT {select_list} FROM analytics.{matview} "
        f"WHERE tenant_id = :tenant_id AND app_id = :app_id LIMIT 50"
    )


async def build_crm_fragment(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str
) -> CrmResolvedFragment | None:
    """Project the tenant's published field map into a resolved fragment, or ``None`` if unmapped."""
    rows = (await db.execute(
        select(CrmFieldMap).where(
            CrmFieldMap.tenant_id == tenant_id, CrmFieldMap.app_id == app_id
        )
    )).scalars().all()
    if not rows:
        return None

    by_grain: dict[str, list[CrmFieldMap]] = {}
    version = 0
    for r in rows:
        by_grain.setdefault(r.record_type, []).append(r)
        version = max(version, r.version or 1)

    grains: list[FragmentGrain] = []
    exemplars: list[tuple[str, str]] = []
    for grain, logical in _LOGICAL_TABLE.items():
        bindings = by_grain.get(grain)
        if not bindings:
            continue
        cols = _grain_columns(grain, bindings)
        mv = resolved_matview_name(grain, tenant_id, app_id)
        grains.append(FragmentGrain(
            logical_table=logical, matview_table=mv, grain_key=_GRAIN_KEY[grain], columns=tuple(cols),
        ))
        exemplars.append((f"resolved_{grain}_sample", _exemplar_sql(mv, cols, _GRAIN_KEY[grain])))

    if not grains:
        return None
    return CrmResolvedFragment(app_id=app_id, version=version, grains=tuple(grains), exemplars=tuple(exemplars))


async def validate_resolved_contract(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str
) -> CrmResolvedFragment | None:
    """Publish-time gate (3.3): the built matview matches the projected fragment AND resolved-column
    SQL passes the SAME enforcers Sherlock runs. Returns the fragment, or ``None`` if no CRM map.

    Raises ``ValueError`` on matview/fragment parity drift and ``ExemplarContractError`` if a
    resolved-column exemplar would be rejected — so a map that can't be served is refused at publish,
    never at a Sherlock turn. Static standard-column exemplars still boot-validate; this never asks
    the boot-fatal validator to see the per-tenant matview.
    """
    fragment = await build_crm_fragment(db, tenant_id=tenant_id, app_id=app_id)
    if fragment is None:
        return None

    for g in fragment.grains:
        cols = set(await matview_columns(db, g.matview_table))
        if not cols:
            raise ValueError(f"resolved matview analytics.{g.matview_table} is not built")
        missing = {c.name for c in g.columns} - cols
        if missing:
            raise ValueError(
                f"matview {g.matview_table} is missing projected columns: {sorted(missing)}"
            )

    from app.services.chat_engine.manifest_validator import validate_exemplars_through_enforcers
    from app.services.chat_engine.workbench_catalog import load_workbench_catalog_strict

    composed = compose_catalog(load_workbench_catalog_strict(app_id), fragment)
    validate_exemplars_through_enforcers(composed, app_id, raise_on_reject=True)
    return fragment


def compose_catalog(catalog, fragment: CrmResolvedFragment):
    """Overlay the fragment onto the static catalog for one turn (rekey to the matview + columns).

    The bouncer (R2) and the lowering scope resolver both key a table reference on the catalog KEY,
    which must equal the physical table the LLM writes (the static invariant is key == base_table).
    So each swapped grain is **rekeyed** to its per-tenant matview name, every relationship that
    referenced the old key is rewritten, the resolved columns replace the legacy ones, stale
    exemplars on the swapped physical tables are dropped, and the fragment's resolved exemplars are
    added. Sherlock then writes ``FROM analytics.dim_lead__<slug>`` over ``condition`` and it resolves
    cleanly. The static catalog is never mutated.
    """
    from app.services.chat_engine.workbench_catalog import (
        BaseTableRef,
        KeyDef,
        LogicalColumn,
        VerifiedQuery,
    )

    rename: dict[str, str] = {}
    swapped_physical: set[str] = set()
    tables = dict(catalog.tables)
    for g in fragment.grains:
        static = catalog.tables.get(g.logical_table)
        if static is None:
            continue
        rename[g.logical_table] = g.matview_table
        swapped_physical.add(static.qualified_table)

        dims, times, facts = [], [], []
        for c in g.columns:
            lc = LogicalColumn(
                name=c.name, expr=c.name, data_type=c.data_type,
                is_enum=c.is_enum, sample_values=list(c.sample_values), synonyms=list(c.synonyms),
            )
            if c.data_type == "temporal":
                times.append(lc)
            elif c.data_type == "quantitative":
                facts.append(lc)
            else:
                dims.append(lc)

        del tables[g.logical_table]
        tables[g.matview_table] = static.model_copy(update={
            "name": g.matview_table,
            "base_table": BaseTableRef(schema="analytics", table=g.matview_table),
            "dimensions": dims, "time_dimensions": times, "facts": facts, "metrics": [],
            "physical_primary_key": KeyDef(columns=[g.grain_key]),
            "analytical_grain": KeyDef(columns=[g.grain_key]),
            "tenant_scoped_unique_key": None,
        })

    relationships = [
        rel.model_copy(update={
            "left_table": rename.get(rel.left_table, rel.left_table),
            "right_table": rename.get(rel.right_table, rel.right_table),
        })
        for rel in catalog.relationships
    ]

    kept = [
        vq for vq in catalog.verified_queries
        if not any(phys in vq.sql for phys in swapped_physical)
    ]
    kept += [
        VerifiedQuery(name=name, question=name.replace("_", " "), sql=sql)
        for name, sql in fragment.exemplars
    ]
    return catalog.model_copy(update={
        "tables": tables, "relationships": relationships, "verified_queries": kept,
    })


__all__ = [
    "FragmentColumn",
    "FragmentGrain",
    "CrmResolvedFragment",
    "build_crm_fragment",
    "compose_catalog",
    "validate_resolved_contract",
]
