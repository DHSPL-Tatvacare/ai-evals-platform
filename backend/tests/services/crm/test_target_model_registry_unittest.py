"""Target-model registry — generic seam keyed by (domain, record_type); crm/lead + crm/activity only."""
from __future__ import annotations

from app.services.crm.grain_schema import grain_schema, registered_target_models, target_model


def test_target_model_crm_lead_matches_grain_schema():
    m = target_model("crm", "lead")
    assert m == grain_schema("lead")
    assert m["record_type"] == "lead"
    assert m["natural_key_target"] == "lead_id"
    assert m["lead_link_required"] is False
    names = {c["target"] for c in m["standard_columns"]}
    assert "phone_number" in names
    assert "lead_stage" in names


def test_target_model_crm_activity_matches_grain_schema():
    m = target_model("crm", "activity")
    assert m == grain_schema("activity")
    assert m["record_type"] == "activity"
    assert m["lead_link_required"] is True
    assert m["natural_key_target"] == "source_activity_id"


def test_unknown_domain_raises():
    try:
        target_model("clinical", "person")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown domain")


def test_unknown_record_type_raises():
    try:
        target_model("crm", "deal")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown record_type")


def test_exactly_lead_and_activity_registered():
    assert sorted(registered_target_models()) == [("crm", "activity"), ("crm", "lead")]
