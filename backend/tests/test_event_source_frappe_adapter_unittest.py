"""Frappe CRM event-source adapter — verbatim Frappe webhook doc shapes.

Frappe outgoing webhooks POST the document JSON. The bound doc-event
(after_insert / on_update / on_trash / on_submit) rides as the
``X-Frappe-Event`` header (Frappe sets it from the webhook's Doc Event), and the
document carries ``doctype``. EVENT_MAP keys on ``{doctype}:{doc_event}``.
"""
from __future__ import annotations

import pytest


def _adapter():
    from app.services.orchestration.adapters import resolve_adapter

    return resolve_adapter(capability="event_source", vendor="frappe")


# Verbatim Frappe Lead doc (frappe CRM Lead doctype core fields).
_LEAD_DOC = {
    "doctype": "Lead",
    "name": "CRM-LEAD-2026-00001",
    "lead_name": "Asha Rao",
    "email_id": "asha@example.com",
    "mobile_no": "+919900000001",
    "status": "Lead",
    "company_name": "Acme Health",
}

_DEAL_DOC = {
    "doctype": "CRM Deal",
    "name": "CRM-DEAL-2026-00007",
    "organization": "Acme Health",
    "status": "Qualification",
}

_TASK_DOC = {
    "doctype": "CRM Task",
    "name": "CRM-TASK-2026-00010",
    "title": "Call back",
    "status": "Todo",
    "reference_docname": "CRM-LEAD-2026-00001",
}


def test_frappe_adapter_registered_clinical_or_crm():
    adapter = _adapter()
    assert adapter.capability == "event_source"
    assert adapter.vendor == "frappe"
    assert adapter.workflow_type == "crm"


def test_frappe_map_lead_after_insert_to_created():
    adapter = _adapter()
    raw = {**_LEAD_DOC, "_frappe_doc_event": "after_insert"}
    assert adapter.map_event_name(raw) == "crm.lead.created"


def test_frappe_map_lead_on_update_to_updated():
    adapter = _adapter()
    raw = {**_LEAD_DOC, "_frappe_doc_event": "on_update"}
    assert adapter.map_event_name(raw) == "crm.lead.updated"


def test_frappe_map_deal_on_update_to_deal_updated():
    adapter = _adapter()
    raw = {**_DEAL_DOC, "_frappe_doc_event": "on_update"}
    assert adapter.map_event_name(raw) == "crm.deal.updated"


def test_frappe_map_task_after_insert_to_task_created():
    adapter = _adapter()
    raw = {**_TASK_DOC, "_frappe_doc_event": "after_insert"}
    assert adapter.map_event_name(raw) == "crm.task.created"


def test_frappe_unknown_doctype_event_maps_none():
    adapter = _adapter()
    raw = {"doctype": "Sales Invoice", "name": "X", "_frappe_doc_event": "on_submit"}
    assert adapter.map_event_name(raw) is None


def test_frappe_normalize_lead_recipient_id_is_doc_name():
    adapter = _adapter()
    raw = {**_LEAD_DOC, "_frappe_doc_event": "after_insert"}
    batch = adapter.normalize_event(raw)
    assert batch.event_name == "crm.lead.created"
    assert len(batch.recipients) == 1
    rec = batch.recipients[0]
    assert rec.recipient_id == "CRM-LEAD-2026-00001"
    # Native doc fields are preserved verbatim in the recipient payload.
    assert rec.payload["lead_name"] == "Asha Rao"
    assert rec.payload["mobile_no"] == "+919900000001"


def test_frappe_ingest_id_is_doctype_name_event():
    adapter = _adapter()
    raw = {**_LEAD_DOC, "_frappe_doc_event": "after_insert"}
    batch = adapter.normalize_event(raw)
    assert batch.ingest_id == "frappe|Lead|CRM-LEAD-2026-00001|after_insert"


def test_frappe_event_name_from_header_when_no_inline_event(monkeypatch):
    adapter = _adapter()
    # Header-driven event resolution (Frappe sets X-Frappe-Event on the POST).
    name = adapter.map_event_name({**_LEAD_DOC}, headers={"x-frappe-event": "after_insert"})
    assert name == "crm.lead.created"
