"""Grain schema — the closed list of bind targets the editor offers (source of truth = ORM)."""
from __future__ import annotations

from app.services.crm.grain_schema import grain_schema


def test_lead_grain_exposes_standard_columns_and_slot_pool():
    s = grain_schema("lead")
    assert s["record_type"] == "lead"
    assert s["natural_key_target"] == "lead_id"
    assert s["lead_link_required"] is False
    names = {c["target"] for c in s["standard_columns"]}
    assert "phone_number" in names
    assert "lead_stage" in names
    assert "phone_number_norm" not in names  # derived by the unpacker, never mapped
    assert "tenant_id" not in names  # plumbing, never a target
    assert len(s["slots"]["text"]) == 30
    assert len(s["slots"]["json"]) == 1
    # each standard column carries a humanised label + a data type
    phone = next(c for c in s["standard_columns"] if c["target"] == "phone_number")
    assert phone["label"] == "Phone number"
    assert phone["data_type"] == "text"


def test_activity_grain_requires_lead_link():
    s = grain_schema("activity")
    assert s["lead_link_required"] is True
    assert s["lead_link_target"] == "lead_id"
    assert s["natural_key_target"] == "source_activity_id"
    assert "lead_id" in s["expected_targets"]
    types = {c["target"]: c["data_type"] for c in s["standard_columns"]}
    assert types["duration_seconds"] == "int"
    assert len(s["slots"]["text"]) == 10  # smaller activity pool


def test_unknown_grain_raises():
    try:
        grain_schema("deal")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown grain")
