"""Clinical patient-journey event-source adapter — native journey events → canonical clinical events."""
from __future__ import annotations

from typing import Any, ClassVar, Mapping, Optional

from app.services.orchestration.adapters.canonical import (
    CanonicalEventBatch,
    CanonicalEventRecipient,
)


class MytatvaEventSourceAdapter:
    capability = "event_source"
    vendor = "mytatva"
    workflow_type: ClassVar[str] = "clinical"
    # Native patient-journey ``event_type`` → canonical clinical event.
    EVENT_MAP: ClassVar[Mapping[str, str]] = {
        "program_enrolled": "clinical.program.enrolled",
        "diagnostic_landing": "clinical.diagnostic.landing",
        "diagnostic_intent": "clinical.diagnostic.intent",
        "diagnostic_details_submitted": "clinical.diagnostic.details_submitted",
        "diagnostic_address_submitted": "clinical.diagnostic.address_submitted",
        "diagnostic_slot_selected": "clinical.diagnostic.slot_selected",
        "diagnostic_booking_confirmed": "clinical.diagnostic.booking_confirmed",
        "lab_test_booked": "clinical.labtest.booked",
        "appointment_booked": "clinical.appointment.booked",
        "drug_claimed": "clinical.drug.claimed",
        "order_punched": "clinical.order.punched",
        "assessment_completed": "clinical.assessment.completed",
        "score_logged": "clinical.score.logged",
        "plan_purchased": "clinical.plan.purchased",
        "refill_due": "clinical.refill.due",
        "dose_missed": "clinical.dose.missed",
        "adherence_check_due": "clinical.adherence.check_due",
        "vital_submitted": "clinical.vital.submitted",
    }

    def map_event_name(
        self, raw: dict[str, Any], *, headers: Optional[Mapping[str, str]] = None,  # noqa: ARG002
    ) -> Optional[str]:
        event_type = raw.get("event_type")
        if not event_type:
            return None
        return self.EVENT_MAP.get(str(event_type))

    def normalize_event(self, raw: dict[str, Any]) -> CanonicalEventBatch:
        event_type = str(raw.get("event_type") or "")
        event_name = self.EVENT_MAP.get(event_type) or ""
        patient_id = str(raw.get("patient_id") or "")
        recipients = (
            [CanonicalEventRecipient(recipient_id=patient_id, payload=dict(raw))]
            if patient_id else []
        )
        ingest_id = f"mytatva|{event_type}|{patient_id}" if event_type and patient_id else None
        return CanonicalEventBatch(
            event_name=event_name, recipients=recipients, ingest_id=ingest_id,
        )

    def verify_signature(self, raw: bytes, headers: Mapping[str, str]) -> bool:  # noqa: ARG002
        # The per-trigger URL token gates the route.
        return True


from app.services.orchestration.adapters import register_adapter  # noqa: E402

register_adapter(
    capability="event_source", vendor="mytatva", adapter=MytatvaEventSourceAdapter(),
)

__all__ = ["MytatvaEventSourceAdapter"]
