"""Clinical patient-journey event-source adapter — verbatim native event shapes.

The clinical source posts a patient-journey event with a native ``event_type``
discriminator and a ``patient_id``. EVENT_MAP translates native journey events
to canonical ``clinical.*`` names.
"""
from __future__ import annotations

import pytest


def _adapter():
    from app.services.orchestration.adapters import resolve_adapter

    return resolve_adapter(capability="event_source", vendor="mytatva")


_ENROLLED = {
    "event_type": "program_enrolled",
    "patient_id": "PT-1001",
    "program": "diabetes-care",
    "phone": "+919900000010",
}

_LABTEST = {
    "event_type": "lab_test_booked",
    "patient_id": "PT-1001",
    "test_code": "HBA1C",
}

_REFILL_DUE = {
    "event_type": "refill_due",
    "patient_id": "PT-1002",
    "drug": "Metformin",
}


def test_mytatva_adapter_registered_clinical():
    adapter = _adapter()
    assert adapter.capability == "event_source"
    assert adapter.vendor == "mytatva"
    assert adapter.workflow_type == "clinical"


def test_mytatva_map_program_enrolled():
    adapter = _adapter()
    assert adapter.map_event_name(_ENROLLED) == "clinical.program.enrolled"


def test_mytatva_map_lab_test_booked():
    adapter = _adapter()
    assert adapter.map_event_name(_LABTEST) == "clinical.labtest.booked"


def test_mytatva_map_refill_due_proposed_adherence():
    adapter = _adapter()
    assert adapter.map_event_name(_REFILL_DUE) == "clinical.refill.due"


def test_mytatva_unknown_event_maps_none():
    adapter = _adapter()
    assert adapter.map_event_name({"event_type": "nonsense", "patient_id": "X"}) is None


def test_mytatva_normalize_recipient_id_is_patient_id():
    adapter = _adapter()
    batch = adapter.normalize_event(_ENROLLED)
    assert batch.event_name == "clinical.program.enrolled"
    assert len(batch.recipients) == 1
    rec = batch.recipients[0]
    assert rec.recipient_id == "PT-1001"
    assert rec.payload["program"] == "diabetes-care"
    assert rec.payload["phone"] == "+919900000010"


def test_mytatva_ingest_id_stable():
    adapter = _adapter()
    batch = adapter.normalize_event(_ENROLLED)
    assert batch.ingest_id == "mytatva|program_enrolled|PT-1001"
