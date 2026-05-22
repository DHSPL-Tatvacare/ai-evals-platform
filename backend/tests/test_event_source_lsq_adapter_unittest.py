"""LeadSquared event-source adapter — verbatim LSQ webhook shapes.

LSQ Lead Automation / Webhook actions POST the lead object using LSQ field
names (``ProspectID``, ``FirstName``, ``EmailAddress``, ``ProspectStage`` …)
plus an ``Event`` discriminator. Activity-driven webhooks can post a grouped
batch under ``Activities`` referencing one ``RelatedProspectId``.
"""
from __future__ import annotations

import pytest


def _adapter():
    from app.services.orchestration.adapters import resolve_adapter

    return resolve_adapter(capability="event_source", vendor="lsq")


# Verbatim LSQ lead-automation webhook (single lead, LSQ field names).
_LEAD_CREATED = {
    "Event": "LeadCreation",
    "ProspectID": "9f0b4c2a-1111-2222-3333-444455556666",
    "FirstName": "Asha",
    "LastName": "Rao",
    "Phone": "+919900000001",
    "EmailAddress": "asha@example.com",
    "ProspectStage": "New",
}

_LEAD_STAGE_CHANGED = {
    "Event": "StageChange",
    "ProspectID": "9f0b4c2a-1111-2222-3333-444455556666",
    "ProspectStage": "Qualified",
}

# Grouped activity batch — LSQ posts multiple activities for one prospect.
_ACTIVITY_BATCH = {
    "Event": "ActivityCreation",
    "RelatedProspectId": "9f0b4c2a-1111-2222-3333-444455556666",
    "Activities": [
        {"ActivityEvent": 21, "ActivityEvent_Note": "Call 1"},
        {"ActivityEvent": 22, "ActivityEvent_Note": "Call 2"},
    ],
}


def test_lsq_adapter_registered_crm():
    adapter = _adapter()
    assert adapter.capability == "event_source"
    assert adapter.vendor == "lsq"
    assert adapter.workflow_type == "crm"


def test_lsq_map_lead_creation():
    adapter = _adapter()
    assert adapter.map_event_name(_LEAD_CREATED) == "crm.lead.created"


def test_lsq_map_stage_change():
    adapter = _adapter()
    assert adapter.map_event_name(_LEAD_STAGE_CHANGED) == "crm.lead.stage_changed"


def test_lsq_map_activity_creation():
    adapter = _adapter()
    assert adapter.map_event_name(_ACTIVITY_BATCH) == "crm.activity.logged"


def test_lsq_unknown_event_maps_none():
    adapter = _adapter()
    assert adapter.map_event_name({"Event": "SomethingExotic"}) is None


def test_lsq_normalize_lead_recipient_id_is_prospect_id():
    adapter = _adapter()
    batch = adapter.normalize_event(_LEAD_CREATED)
    assert batch.event_name == "crm.lead.created"
    assert len(batch.recipients) == 1
    rec = batch.recipients[0]
    assert rec.recipient_id == "9f0b4c2a-1111-2222-3333-444455556666"
    assert rec.payload["FirstName"] == "Asha"
    assert rec.payload["Phone"] == "+919900000001"


def test_lsq_grouped_activity_batch_fans_to_one_recipient_per_activity():
    adapter = _adapter()
    batch = adapter.normalize_event(_ACTIVITY_BATCH)
    assert batch.event_name == "crm.activity.logged"
    # All activities reference one prospect → one recipient, activities preserved.
    assert len(batch.recipients) == 1
    rec = batch.recipients[0]
    assert rec.recipient_id == "9f0b4c2a-1111-2222-3333-444455556666"
    assert len(rec.payload["Activities"]) == 2


def test_lsq_ingest_id_stable_for_lead():
    adapter = _adapter()
    batch = adapter.normalize_event(_LEAD_CREATED)
    assert batch.ingest_id == "lsq|LeadCreation|9f0b4c2a-1111-2222-3333-444455556666"
