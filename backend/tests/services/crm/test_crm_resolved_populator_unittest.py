"""3.1 — the resolved-surface projector: deterministic names + map-driven column projection.

Pure-function coverage (no DB): the matview/live-view names are deterministic, schema-safe,
and grain-distinct; the projection passes standard columns through and renames each typed slot
to its semantic key (``e.txt_01 AS condition``); the generated DDL is schema-qualified and
tenant-scoped. The resolved layer's only variable is the field map — there is no provider branch.
"""
from __future__ import annotations

import re
import uuid

import pytest

from app.models.crm import CrmFieldMap
from app.services.crm.crm_resolved_populator import (
    build_live_view_ddl,
    build_matview_ddl,
    resolved_live_view_name,
    resolved_matview_name,
    resolved_projection,
)

_TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
_APP = "inside-sales"
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _binding(slot: str, semantic: str, data_type: str = "text") -> CrmFieldMap:
    return CrmFieldMap(
        id=uuid.uuid4(), tenant_id=_TENANT, app_id=_APP, connection_id=uuid.uuid4(),
        record_type="lead", slot=slot, semantic_key=semantic,
        source_field="x", data_type=data_type, value_map=None,
    )


def test_matview_name_is_deterministic_safe_and_grain_distinct():
    a = resolved_matview_name("lead", _TENANT, _APP)
    b = resolved_matview_name("lead", _TENANT, _APP)
    assert a == b                                   # deterministic
    assert _IDENT.match(a) and len(a) <= 63          # valid unquoted pg identifier
    assert a.startswith("dim_lead__")
    act = resolved_matview_name("activity", _TENANT, _APP)
    assert act.startswith("fact_lead_activity__")
    assert act != a                                  # grain-distinct
    # tenant-distinct
    other = resolved_matview_name("lead", uuid.uuid4(), _APP)
    assert other != a


def test_live_view_name_is_distinct_from_matview():
    mv = resolved_matview_name("lead", _TENANT, _APP)
    lv = resolved_live_view_name("lead", _TENANT, _APP)
    assert lv != mv and _IDENT.match(lv) and len(lv) <= 63


def test_projection_passes_standard_columns_and_renames_slots():
    bindings = [
        _binding("lead_id", "lead_id"),           # standard — passthrough, not renamed
        _binding("lead_stage", "lead_stage"),     # standard
        _binding("txt_01", "condition"),          # slot → semantic name
        _binding("txt_03", "plan_name"),          # slot → semantic name
    ]
    proj = resolved_projection("lead", bindings)
    aliases = [alias for _expr, alias in proj]
    # scope columns are always exposed (orphan-guard joins on them; R7 filters on them)
    assert "tenant_id" in aliases and "app_id" in aliases
    # every standard core column is projected from the lead alias
    assert ("l.lead_id", "lead_id") in proj
    assert ("l.lead_stage", "lead_stage") in proj
    assert ("l.phone_number_norm", "phone_number_norm") in proj
    # slots are renamed to their semantic key off the ext alias — txt_NN never surfaces
    assert ("e.txt_01", "condition") in proj
    assert ("e.txt_03", "plan_name") in proj
    assert not any(alias.startswith("txt_") for alias in aliases)


def test_matview_ddl_is_schema_qualified_and_tenant_scoped():
    bindings = [_binding("txt_01", "condition")]
    ddl = build_matview_ddl("lead", _TENANT, _APP, bindings)
    name = resolved_matview_name("lead", _TENANT, _APP)
    assert f"CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.{name}" in ddl
    assert "FROM platform.crm_lead l" in ddl
    assert "LEFT JOIN platform.crm_lead_ext e ON e.crm_lead_id = l.id" in ddl
    assert f"l.tenant_id = '{_TENANT}'::uuid" in ddl
    assert f"l.app_id = '{_APP}'" in ddl
    assert "e.txt_01 AS condition" in ddl


def test_activity_ddl_joins_the_activity_tables():
    ddl = build_matview_ddl("activity", _TENANT, _APP, [])
    assert "FROM platform.crm_activity l" in ddl
    assert "LEFT JOIN platform.crm_activity_ext e ON e.crm_activity_id = l.id" in ddl
    assert "l.duration_seconds AS duration_seconds" in ddl


def test_live_view_ddl_is_create_or_replace_view():
    ddl = build_live_view_ddl("lead", _TENANT, _APP, [])
    lv = resolved_live_view_name("lead", _TENANT, _APP)
    assert f"CREATE OR REPLACE VIEW analytics.{lv}" in ddl
    assert "FROM platform.crm_lead l" in ddl
