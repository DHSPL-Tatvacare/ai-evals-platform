"""Engineering-owned canonical event catalog, keyed by lowercase workflow_type.

The catalog is the source of truth for the event-trigger node combobox and the
boot/test alignment guard. Keys are the literal ``workflow_type`` values
(``crm`` / ``clinical``, lowercase). Keying on ``CRM`` / ``CLINICAL`` silently
returns an empty list — that is load-bearing, not a bug: the workflow_type
column stores the lowercase value and any case drift surfaces as an empty
combobox rather than a crash.

Native -> canonical mapping lives in each vendor adapter's ``EVENT_MAP``, not
here. This catalog only enumerates the vendor-agnostic names authors can bind a
trigger to.
"""
from __future__ import annotations


_CRM_EVENTS: tuple[str, ...] = (
    "crm.lead.created",
    "crm.lead.updated",
    "crm.lead.field_changed",
    "crm.lead.stage_changed",
    "crm.lead.owner_changed",
    "crm.lead.score_changed",
    "crm.lead.deleted",
    "crm.lead.merged",
    "crm.deal.created",
    "crm.deal.updated",
    "crm.deal.stage_changed",
    "crm.task.created",
    "crm.task.completed",
    "crm.task.cancelled",
    "crm.task.reminder",
    "crm.activity.logged",
    "crm.landing_page.submitted",
    "crm.contact.created",
    "crm.call.logged",
    "crm.message.received",
)

_CLINICAL_EVENTS: tuple[str, ...] = (
    # Confirmed (vault data-model).
    "clinical.program.enrolled",
    "clinical.diagnostic.landing",
    "clinical.diagnostic.intent",
    "clinical.diagnostic.details_submitted",
    "clinical.diagnostic.address_submitted",
    "clinical.diagnostic.slot_selected",
    "clinical.diagnostic.booking_confirmed",
    "clinical.labtest.booked",
    "clinical.appointment.booked",
    "clinical.drug.claimed",
    "clinical.order.punched",
    "clinical.assessment.completed",
    "clinical.score.logged",
    "clinical.plan.purchased",
    # Proposed adherence (user-confirmed to seed).
    "clinical.refill.due",
    "clinical.dose.missed",
    "clinical.adherence.check_due",
    "clinical.vital.submitted",
)

_CATALOG: dict[str, tuple[str, ...]] = {
    "crm": _CRM_EVENTS,
    "clinical": _CLINICAL_EVENTS,
}


class EventCatalogAlignmentError(RuntimeError):
    """An adapter's EVENT_MAP references a canonical name absent from the catalog."""


def catalog_for_workflow_type(workflow_type: str) -> list[str]:
    """Canonical event names for a workflow_type. Empty list for unknown keys."""
    return list(_CATALOG.get(workflow_type, ()))


def workflow_types() -> list[str]:
    return sorted(_CATALOG.keys())


def assert_adapters_aligned_with_catalog() -> None:
    """Every registered event_source adapter's EVENT_MAP values must be in the
    catalog for the adapter's workflow_type. Raises on drift; no-op when aligned."""
    from app.services.orchestration.adapters import resolve_adapter, registered_adapters

    drift: list[str] = []
    for capability, vendor in registered_adapters():
        if capability != "event_source":
            continue
        adapter = resolve_adapter(capability=capability, vendor=vendor)
        wf_type = getattr(adapter, "workflow_type", None)
        event_map = getattr(adapter, "EVENT_MAP", {}) or {}
        allowed = set(catalog_for_workflow_type(wf_type or ""))
        for native_key, canonical in event_map.items():
            if canonical not in allowed:
                drift.append(
                    f"{vendor}.EVENT_MAP[{native_key!r}]={canonical!r} "
                    f"not in catalog[{wf_type!r}]"
                )
    if drift:
        raise EventCatalogAlignmentError("; ".join(drift))


__all__ = [
    "EventCatalogAlignmentError",
    "assert_adapters_aligned_with_catalog",
    "catalog_for_workflow_type",
    "workflow_types",
]
