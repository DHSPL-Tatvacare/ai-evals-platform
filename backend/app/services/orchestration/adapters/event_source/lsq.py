"""LeadSquared event-source adapter — LSQ lead/activity webhook shapes → canonical CRM events."""
from __future__ import annotations

from typing import Any, ClassVar, Mapping, Optional

from app.services.orchestration.adapters.canonical import (
    CanonicalEventBatch,
    CanonicalEventRecipient,
)


class LsqEventSourceAdapter:
    capability = "event_source"
    vendor = "lsq"
    workflow_type: ClassVar[str] = "crm"
    # LSQ native ``Event`` discriminator → canonical CRM event.
    EVENT_MAP: ClassVar[Mapping[str, str]] = {
        "LeadCreation": "crm.lead.created",
        "LeadUpdate": "crm.lead.updated",
        "StageChange": "crm.lead.stage_changed",
        "OwnerChange": "crm.lead.owner_changed",
        "ScoreChange": "crm.lead.score_changed",
        "ActivityCreation": "crm.activity.logged",
        "LandingPageSubmission": "crm.landing_page.submitted",
    }

    def map_event_name(
        self, raw: dict[str, Any], *, headers: Optional[Mapping[str, str]] = None,  # noqa: ARG002
    ) -> Optional[str]:
        event = raw.get("Event")
        if not event:
            return None
        return self.EVENT_MAP.get(str(event))

    def normalize_event(
        self, raw: dict[str, Any], *, headers: Optional[Mapping[str, str]] = None,  # noqa: ARG002
    ) -> CanonicalEventBatch:
        event = str(raw.get("Event") or "")
        event_name = self.EVENT_MAP.get(event) or ""
        # Grouped activity batches reference one prospect via RelatedProspectId;
        # lead webhooks carry the prospect id under ProspectID.
        prospect_id = str(raw.get("ProspectID") or raw.get("RelatedProspectId") or "")
        recipients = (
            [CanonicalEventRecipient(recipient_id=prospect_id, payload=dict(raw))]
            if prospect_id else []
        )
        ingest_id = f"lsq|{event}|{prospect_id}" if event and prospect_id else None
        return CanonicalEventBatch(
            event_name=event_name, recipients=recipients, ingest_id=ingest_id,
        )

    def verify_signature(self, raw: bytes, headers: Mapping[str, str]) -> bool:  # noqa: ARG002
        # LSQ webhook actions carry no standard HMAC; the per-trigger URL token
        # gates the route.
        return True


from app.services.orchestration.adapters import register_adapter  # noqa: E402

register_adapter(
    capability="event_source", vendor="lsq", adapter=LsqEventSourceAdapter(),
)

__all__ = ["LsqEventSourceAdapter"]
