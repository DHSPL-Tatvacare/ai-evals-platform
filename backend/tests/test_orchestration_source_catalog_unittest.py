"""Phase 11 — source catalog scaffolding tests."""
from __future__ import annotations

import pytest

from app.services.orchestration.source_catalog import (
    SourceCatalogError,
    all_source_refs,
    get_source,
    list_sources,
    lookup_source,
    reverse_lookup_by_table,
)


def test_seeded_refs_present():
    refs = set(all_source_refs())
    assert {"crm.lead_record", "clinical.dim_patient"}.issubset(refs)


def test_get_source_returns_canonical_table():
    s = get_source("crm.lead_record")
    assert s.schema_qualified_table == "analytics.crm_lead_record"
    assert s.id_column == "prospect_id"
    assert "first_name" in s.allowed_payload_columns
    assert "prospect_stage" in s.allowed_filter_columns
    assert "created_on" in s.allowed_lookback_columns


def test_clinical_source():
    s = get_source("clinical.dim_patient")
    assert s.schema_qualified_table == "clinical.dim_patient"
    assert s.id_column == "patient_id"
    assert "primary_condition" in s.allowed_filter_columns


def test_get_source_unknown_raises():
    with pytest.raises(SourceCatalogError):
        get_source("nope.unknown")


def test_lookup_source_returns_none_for_unknown():
    assert lookup_source("nope.unknown") is None


def test_list_sources_filters_by_workflow_type():
    crm = list_sources(workflow_type="crm")
    clinical = list_sources(workflow_type="clinical")
    assert any(s.source_ref == "crm.lead_record" for s in crm)
    assert all(s.source_ref != "crm.lead_record" for s in clinical)
    assert any(s.source_ref == "clinical.dim_patient" for s in clinical)


def test_list_sources_filters_by_app_id():
    visible = list_sources(app_id="inside-sales")
    refs = {s.source_ref for s in visible}
    assert "crm.lead_record" in refs
    assert "clinical.dim_patient" in refs


def test_reverse_lookup_recovers_legacy_table_to_ref():
    s = reverse_lookup_by_table("analytics.crm_lead_record")
    assert s is not None
    assert s.source_ref == "crm.lead_record"
    assert reverse_lookup_by_table("public.does_not_exist") is None
