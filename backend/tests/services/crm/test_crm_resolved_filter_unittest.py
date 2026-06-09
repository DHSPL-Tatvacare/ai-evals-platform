"""The resolved filter lives in the resolved contract (decision §5).

A definition's filter predicate compiles into the matview/live-view ``WHERE`` so the resolved
surface itself only exposes matching rows — Activate alone makes the data match the filter, no
re-sync. The predicate references resolved column names; it compiles to the underlying column
expressions, and can only reference columns the projection actually exposes.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.crm import CrmFieldMap
from app.services.crm.crm_resolved_populator import build_live_view_ddl, build_matview_ddl
from app.services.orchestration.predicate_sql import PredicateSqlError

_TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
_APP = "inside-sales"

_PRED = {
    "and": [
        {"field": "lead_stage", "op": "in", "value": ["won", "lost"]},
        {"field": "condition", "op": "exists"},
    ]
}
_COMPILED = "AND (l.lead_stage IN ('won', 'lost') AND e.txt_01 IS NOT NULL)"


def _binding(slot: str, semantic: str, data_type: str = "text") -> CrmFieldMap:
    return CrmFieldMap(
        id=uuid.uuid4(), tenant_id=_TENANT, app_id=_APP, connection_id=uuid.uuid4(),
        record_type="lead", slot=slot, semantic_key=semantic,
        source_field="x", data_type=data_type, value_map=None,
    )


def test_matview_where_appends_compiled_predicate():
    bindings = [_binding("lead_stage", "lead_stage"), _binding("txt_01", "condition")]
    ddl = build_matview_ddl("lead", _TENANT, _APP, bindings, predicate=_PRED)
    assert f"l.tenant_id = '{_TENANT}'::uuid" in ddl  # scope filter intact
    assert _COMPILED in ddl                            # filter compiled to underlying exprs


def test_live_view_where_appends_compiled_predicate():
    bindings = [_binding("lead_stage", "lead_stage"), _binding("txt_01", "condition")]
    ddl = build_live_view_ddl("lead", _TENANT, _APP, bindings, predicate=_PRED)
    assert _COMPILED in ddl


def test_no_predicate_leaves_where_unchanged():
    ddl = build_matview_ddl("lead", _TENANT, _APP, [_binding("txt_01", "condition")])
    after_where = ddl.split("WHERE", 1)[1]
    assert " AND (" not in after_where  # only the scope predicate, no filter clause


def test_predicate_referencing_unmapped_field_rejected():
    bindings = [_binding("txt_01", "condition")]
    with pytest.raises(PredicateSqlError):
        build_matview_ddl("lead", _TENANT, _APP, bindings, predicate={"field": "ssn", "op": "eq", "value": "x"})
