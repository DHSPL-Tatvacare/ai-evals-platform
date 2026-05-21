"""source.cohort config validation — inline + saved modes, draft deferral, strictness."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

import app.services.orchestration.nodes  # noqa: F401 — register handlers
from app.services.orchestration.node_registry import NODE_REGISTRY
from app.services.orchestration.nodes.source_cohort import SourceCohortConfig


_DRAFT = {"mode": "draft"}


def _validate(raw: dict, *, context: dict | None = None) -> SourceCohortConfig:
    return SourceCohortConfig.model_validate(raw, context=context)


def test_saved_mode_with_version_id_passes():
    cfg = _validate(
        {"mode": "saved", "cohort_definition_version_id": str(uuid.uuid4())}
    )
    assert cfg.mode == "saved"
    assert cfg.cohort_definition_version_id is not None


def test_saved_mode_without_version_id_fails_publish():
    with pytest.raises(ValidationError):
        _validate({"mode": "saved"})


def test_inline_mode_with_source_ref_passes():
    cfg = _validate({"mode": "inline", "source_ref": "crm.lead_record"})
    assert cfg.mode == "inline"
    assert cfg.source_ref == "crm.lead_record"


def test_inline_mode_with_full_query_passes():
    cfg = _validate({
        "mode": "inline",
        "source_ref": "crm.lead_record",
        "payload_fields": ["phone", "name"],
        "filters": [{"column": "stage", "op": "eq", "value": "new"}],
        "lookback_hours": 48,
        "lookback_column": "created_at",
        "consent_gate_channel": "whatsapp",
    })
    assert cfg.payload_fields == ["phone", "name"]
    assert len(cfg.filters) == 1
    assert cfg.filters[0].column == "stage"


def test_inline_mode_without_source_ref_fails_publish():
    with pytest.raises(ValidationError):
        _validate({"mode": "inline"})


def test_draft_defers_cross_field_checks():
    # Half-authored: no mode picked yet, no selectors filled — draft tolerates.
    cfg = _validate({}, context=_DRAFT)
    assert cfg.mode is None


def test_draft_saved_without_version_id_defers():
    cfg = _validate({"mode": "saved"}, context=_DRAFT)
    assert cfg.mode == "saved"
    assert cfg.cohort_definition_version_id is None


def test_draft_inline_without_source_ref_defers():
    cfg = _validate({"mode": "inline"}, context=_DRAFT)
    assert cfg.mode == "inline"


def test_extra_keys_rejected():
    with pytest.raises(ValidationError):
        _validate({"mode": "inline", "source_ref": "crm.lead_record", "bogus": 1})


def test_legacy_compiler_fields_rejected():
    # source_table / id_column / payload_columns / next_node_id are not exposed.
    with pytest.raises(ValidationError):
        _validate({
            "mode": "inline",
            "source_ref": "crm.lead_record",
            "source_table": "analytics.crm_lead_record",
        })


def test_handler_registered_under_source_cohort():
    assert ("*", "source.cohort") in NODE_REGISTRY
    assert ("*", "source.saved_cohort") not in NODE_REGISTRY
    handler = NODE_REGISTRY[("*", "source.cohort")]
    assert handler.node_type == "source.cohort"
    assert handler.output_edges == ["default"]
    assert handler.category == "source"
