"""CRM canonical storage: ORM shape + closed-list field-map validation (Leg 3, Phase 1)."""
from __future__ import annotations

import pytest

from app.models.crm import (
    CrmActivity,
    CrmActivityExt,
    CrmFieldMap,
    CrmLead,
    CrmLeadExt,
    CrmSourceRecord,
)

_LEAD_STANDARD_19 = {
    "first_name", "last_name", "full_name", "email",
    "phone_number", "phone_number_norm",
    "source", "sub_source",
    "lead_stage", "lead_substage", "status", "lost_reason",
    "owner_id", "owner_name",
    "converted", "converted_at", "created_at", "updated_at", "last_activity_at",
}

_ALL_MODELS = [
    CrmSourceRecord, CrmLead, CrmLeadExt, CrmActivity, CrmActivityExt, CrmFieldMap,
]


def _cols(model) -> set[str]:
    return set(model.__table__.columns.keys())


def test_all_six_tables_live_in_platform_schema():
    for model in _ALL_MODELS:
        assert model.__table__.schema == "platform", model.__name__


def test_crm_lead_has_surrogate_pk_and_business_key():
    pk = [c.name for c in CrmLead.__table__.primary_key.columns]
    assert pk == ["id"], "surrogate id must be the sole PK"
    cols = _cols(CrmLead)
    assert "lead_id" in cols
    assert "lead_id" not in pk, "lead_id is the business key, never the PK"
    assert {"tenant_id", "app_id"} <= cols


def test_crm_lead_carries_the_19_standard_columns():
    assert _LEAD_STANDARD_19 <= _cols(CrmLead)


def test_crm_lead_has_verbatim_and_normalised_phone():
    cols = _cols(CrmLead)
    assert "phone_number" in cols and "phone_number_norm" in cols
    assert "phone" not in cols, "column is phone_number, never phone"


def test_crm_lead_business_key_is_unique():
    uniques = {
        tuple(c.name for c in con.columns)
        for con in CrmLead.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("tenant_id", "app_id", "lead_id") in uniques


def test_crm_lead_ext_full_slot_pool():
    cols = _cols(CrmLeadExt)
    for i in range(1, 31):
        assert f"txt_{i:02d}" in cols
    for i in range(1, 21):
        assert f"num_{i:02d}" in cols and f"int_{i:02d}" in cols and f"dt_{i:02d}" in cols
    for i in range(1, 11):
        assert f"bool_{i:02d}" in cols
    assert "json_01" in cols
    assert "txt_31" not in cols and "num_21" not in cols
    assert "crm_lead_id" in cols


def test_crm_activity_standard_columns():
    cols = _cols(CrmActivity)
    assert {"lead_id", "source_activity_id", "direction", "status",
            "duration_seconds", "occurred_at", "tenant_id", "app_id"} <= cols


def test_crm_activity_ext_smaller_slot_pool():
    cols = _cols(CrmActivityExt)
    assert "txt_10" in cols and "txt_11" not in cols
    assert "num_05" in cols and "num_06" not in cols
    assert "json_01" in cols and "crm_activity_id" in cols


def test_crm_source_record_landing_shape():
    cols = _cols(CrmSourceRecord)
    assert {"connection_id", "source_object", "record_type", "source_record_id",
            "raw_payload", "tenant_id", "app_id"} <= cols


def test_crm_field_map_shape():
    cols = _cols(CrmFieldMap)
    assert {"connection_id", "record_type", "slot", "semantic_key", "source_field",
            "data_type", "value_map", "version", "tenant_id", "app_id"} <= cols


# ── closed-list binding validation ───────────────────────────────


def test_validate_binding_accepts_a_slot_and_a_standard_column():
    from app.services.crm.field_map_validation import validate_binding

    validate_binding("lead", "txt_01")
    validate_binding("lead", "phone_number")
    validate_binding("activity", "duration_seconds")
    validate_binding("activity", "txt_05")


def test_validate_binding_rejects_a_target_outside_the_closed_list():
    from app.services.crm.field_map_validation import validate_binding

    with pytest.raises(ValueError):
        validate_binding("lead", "txt_99")
    with pytest.raises(ValueError):
        validate_binding("lead", "made_up_column")
    with pytest.raises(ValueError):
        validate_binding("activity", "txt_20")  # outside the smaller activity pool


def test_validate_binding_rejects_non_lead_activity_record_type():
    from app.services.crm.field_map_validation import validate_binding

    with pytest.raises(ValueError):
        validate_binding("stage_transition", "txt_01")
    with pytest.raises(ValueError):
        validate_binding("deal", "txt_01")
