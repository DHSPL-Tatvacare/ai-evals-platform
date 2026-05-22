"""Identity (webhook) event-source adapter — already-canonical payloads pass through."""
from __future__ import annotations

import pytest


def _adapter():
    from app.services.orchestration.adapters import resolve_adapter

    return resolve_adapter(capability="event_source", vendor="webhook")


def test_webhook_adapter_registered():
    adapter = _adapter()
    assert adapter.capability == "event_source"
    assert adapter.vendor == "webhook"


def test_identity_passthrough_canonical_recipients_list():
    adapter = _adapter()
    raw = {
        "event_name": "crm.lead.created",
        "recipients": [
            {"recipient_id": "LEAD-1", "payload": {"name": "Asha", "phone": "+91999"}},
            {"recipient_id": "LEAD-2", "payload": {"name": "Bo"}},
        ],
    }
    assert adapter.map_event_name(raw) == "crm.lead.created"
    batch = adapter.normalize_event(raw)
    assert batch.event_name == "crm.lead.created"
    assert [r.recipient_id for r in batch.recipients] == ["LEAD-1", "LEAD-2"]
    assert batch.recipients[0].payload == {"name": "Asha", "phone": "+91999"}


def test_identity_passthrough_top_level_recipient_id():
    adapter = _adapter()
    raw = {"event_name": "crm.lead.updated", "recipient_id": "LEAD-9", "stage": "Won"}
    batch = adapter.normalize_event(raw)
    assert batch.event_name == "crm.lead.updated"
    assert len(batch.recipients) == 1
    assert batch.recipients[0].recipient_id == "LEAD-9"
    assert batch.recipients[0].payload["stage"] == "Won"


def test_identity_event_name_from_eventname_alias():
    adapter = _adapter()
    raw = {"eventName": "crm.lead.created", "recipient_id": "L"}
    assert adapter.map_event_name(raw) == "crm.lead.created"


def test_identity_verify_signature_open():
    adapter = _adapter()
    assert adapter.verify_signature(b"{}", {}) is True
