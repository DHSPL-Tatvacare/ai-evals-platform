"""Phase 11 — registered cohort sources.

A ``source.cohort_query`` node selects a cohort source by a stable
``source_ref`` key (e.g. ``crm.lead_record``). The catalog says which
underlying ``schema.table`` and id column back that ref, plus the columns
authors are allowed to project into payload, filter on, or use as a lookback
column. Authors never name raw tables or column lists themselves — that
keeps "what fields exist on a recipient" a tenant-stable contract instead
of a per-workflow free-form string.

Design intent:

  - The catalog is **engineering-owned**, not user-editable. Adding a source
    is a code change reviewed alongside any new fact / dimension table.
  - The catalog drives both **runtime SQL compilation** (cohort query) and
    **builder authoring affordances** (which fields show up in the
    payload-field picker, which columns are filter-able).
  - Per-app sources scope authoring: a workflow under ``app_id='inside-sales'``
    sees CRM sources; a workflow under a clinical app sees clinical sources.
    A single source may be shared across apps when its row-level security
    naturally filters by ``app_id`` (the cohort compiler always adds the
    tenant + app filter, regardless of catalog config).
  - The legacy ``source_table`` / ``id_column`` config remains supported via
    the normalization layer so old saved definitions and seed JSON load
    without churn — but new authoring should produce ``source_ref``.

This is the Commit 1 catalog scaffolding. A later commit will surface it
through an API route for builder dropdowns; this commit only wires the
in-process registry needed by the contract.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CohortSource(BaseModel):
    """One registered cohort source.

    ``schema_qualified_table`` is always written ``schema.table`` (never
    bare) so cohort-query SQL is schema-qualified per the project invariant.
    ``allowed_payload_columns`` and ``allowed_filter_columns`` may overlap.
    ``allowed_lookback_columns`` lists timestamp columns valid for the
    ``lookback_hours`` mechanic; if empty, lookback is not supported on
    this source.
    """
    source_ref: str
    display_label: str
    description: str
    workflow_types: list[str]  # ["crm"], ["clinical"], or both
    app_ids: list[str]
    schema_qualified_table: str
    id_column: str
    allowed_payload_columns: list[str] = Field(default_factory=list)
    allowed_filter_columns: list[str] = Field(default_factory=list)
    allowed_lookback_columns: list[str] = Field(default_factory=list)


_CATALOG: dict[str, CohortSource] = {
    "crm.lead_record": CohortSource(
        source_ref="crm.lead_record",
        display_label="CRM Leads",
        description="Lead records ingested from LeadSquared (analytics.crm_lead_record).",
        workflow_types=["crm"],
        app_ids=["inside-sales"],
        schema_qualified_table="analytics.crm_lead_record",
        id_column="lead_id",
        allowed_payload_columns=[
            "first_name", "last_name", "city", "phone", "whatsapp_number",
            "mql_score", "hba1c", "prospect_stage", "created_on",
            "callback_adherence_seconds", "days_since_last_contact",
            "preferred_language", "lead_source",
        ],
        allowed_filter_columns=[
            "prospect_stage", "mql_score", "hba1c", "city",
            "lead_source", "created_on", "preferred_language",
        ],
        allowed_lookback_columns=["created_on"],
    ),
    "clinical.dim_patient": CohortSource(
        source_ref="clinical.dim_patient",
        display_label="Clinical Patients",
        description="Active patient roster (clinical.dim_patient). Outbox-backed in v1.",
        workflow_types=["clinical"],
        app_ids=["inside-sales"],  # mounted under inside-sales until a dedicated care-pathways app pack ships
        schema_qualified_table="clinical.dim_patient",
        id_column="patient_id",
        allowed_payload_columns=[
            "first_name", "last_name", "preferred_language",
            "primary_condition", "active",
            "hba1c_latest", "hba1c_prior", "ldl_latest",
            "weight_kg", "bmi", "sbp_latest", "dbp_latest",
            "last_visit_at",
        ],
        allowed_filter_columns=[
            "primary_condition", "active", "hba1c_latest",
            "ldl_latest", "preferred_language",
        ],
        allowed_lookback_columns=["last_visit_at"],
    ),
}


class SourceCatalogError(KeyError):
    pass


def get_source(source_ref: str) -> CohortSource:
    if source_ref not in _CATALOG:
        raise SourceCatalogError(f"unknown source_ref: {source_ref!r}")
    return _CATALOG[source_ref]


def lookup_source(source_ref: str) -> Optional[CohortSource]:
    return _CATALOG.get(source_ref)


def list_sources(
    *,
    workflow_type: Optional[str] = None,
    app_id: Optional[str] = None,
) -> list[CohortSource]:
    """Filter sources by workflow type and / or app id."""
    out: list[CohortSource] = []
    for s in _CATALOG.values():
        if workflow_type and workflow_type not in s.workflow_types:
            continue
        if app_id and app_id not in s.app_ids:
            continue
        out.append(s)
    return sorted(out, key=lambda s: s.source_ref)


def all_source_refs() -> list[str]:
    return sorted(_CATALOG.keys())


def reverse_lookup_by_table(schema_qualified_table: str) -> Optional[CohortSource]:
    """Find the catalog entry whose ``schema_qualified_table`` matches.

    Used by the normalizer to upgrade legacy definitions that still carry
    ``source_table`` + ``id_column`` to the new ``source_ref`` form.
    """
    for s in _CATALOG.values():
        if s.schema_qualified_table == schema_qualified_table:
            return s
    return None


__all__ = [
    "CohortSource",
    "SourceCatalogError",
    "get_source",
    "lookup_source",
    "list_sources",
    "all_source_refs",
    "reverse_lookup_by_table",
]
