"""Frappe CRM event-source adapter — Lead/Deal/Task/Contact docs → canonical CRM events.

Frappe outgoing webhooks POST the document JSON (carrying ``doctype`` + ``name``).
The bound doc-event rides as the ``X-Frappe-Event`` header, or inline as
``_frappe_doc_event`` when the webhook config injects it into the body.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping, Optional

from app.services.orchestration.adapters.canonical import (
    CanonicalEventBatch,
    CanonicalEventRecipient,
)

_EVENT_HEADER = "x-frappe-event"
_INLINE_EVENT_KEYS = ("_frappe_doc_event", "doc_event")


def _doc_event(raw: dict[str, Any], headers: Optional[Mapping[str, str]]) -> Optional[str]:
    for key in _INLINE_EVENT_KEYS:
        val = raw.get(key)
        if val:
            return str(val)
    if headers:
        lowered = {str(k).lower(): v for k, v in headers.items()}
        val = lowered.get(_EVENT_HEADER)
        if val:
            return str(val)
    return None


class FrappeEventSourceAdapter:
    capability = "event_source"
    vendor = "frappe"
    workflow_type: ClassVar[str] = "crm"
    # {doctype}:{doc_event} → canonical CRM event.
    EVENT_MAP: ClassVar[Mapping[str, str]] = {
        "Lead:after_insert": "crm.lead.created",
        "Lead:on_update": "crm.lead.updated",
        "Lead:on_trash": "crm.lead.deleted",
        "CRM Lead:after_insert": "crm.lead.created",
        "CRM Lead:on_update": "crm.lead.updated",
        "CRM Lead:on_trash": "crm.lead.deleted",
        "CRM Deal:after_insert": "crm.deal.created",
        "CRM Deal:on_update": "crm.deal.updated",
        "Opportunity:after_insert": "crm.deal.created",
        "Opportunity:on_update": "crm.deal.updated",
        "CRM Task:after_insert": "crm.task.created",
        "CRM Task:on_update": "crm.task.completed",
        "ToDo:after_insert": "crm.task.created",
        "Contact:after_insert": "crm.contact.created",
        "CRM Call Log:after_insert": "crm.call.logged",
    }

    def map_event_name(
        self, raw: dict[str, Any], *, headers: Optional[Mapping[str, str]] = None,
    ) -> Optional[str]:
        doctype = raw.get("doctype")
        doc_event = _doc_event(raw, headers)
        if not doctype or not doc_event:
            return None
        return self.EVENT_MAP.get(f"{doctype}:{doc_event}")

    def normalize_event(self, raw: dict[str, Any]) -> CanonicalEventBatch:
        doctype = str(raw.get("doctype") or "")
        doc_event = _doc_event(raw, None) or ""
        doc_name = str(raw.get("name") or "")
        event_name = self.EVENT_MAP.get(f"{doctype}:{doc_event}") or ""
        payload = {
            k: v for k, v in raw.items()
            if k not in _INLINE_EVENT_KEYS
        }
        recipients = (
            [CanonicalEventRecipient(recipient_id=doc_name, payload=payload)]
            if doc_name else []
        )
        ingest_id = (
            f"frappe|{doctype}|{doc_name}|{doc_event}" if doc_name and doc_event else None
        )
        return CanonicalEventBatch(
            event_name=event_name, recipients=recipients, ingest_id=ingest_id,
        )

    def verify_signature(self, raw: bytes, headers: Mapping[str, str]) -> bool:  # noqa: ARG002
        # Frappe webhook secret (X-Frappe-Webhook-Signature) is optional; the
        # per-trigger URL token gates the route. HMAC verification can layer on
        # later without changing the canonical contract.
        return True


from app.services.orchestration.adapters import register_adapter  # noqa: E402

register_adapter(
    capability="event_source", vendor="frappe", adapter=FrappeEventSourceAdapter(),
)

__all__ = ["FrappeEventSourceAdapter"]
