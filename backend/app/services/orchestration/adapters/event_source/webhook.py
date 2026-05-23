"""Identity event-source adapter — the payload is already canonical."""
from __future__ import annotations

from typing import Any, ClassVar, Mapping, Optional

from app.services.orchestration.adapters.canonical import (
    CanonicalEventBatch,
    CanonicalEventRecipient,
)


def _event_name(raw: dict[str, Any]) -> Optional[str]:
    name = raw.get("event_name") or raw.get("eventName")
    return str(name) if name else None


class WebhookEventSourceAdapter:
    capability = "event_source"
    vendor = "webhook"
    # Identity passthrough is vendor-agnostic; it is not catalog-gated and
    # carries no native→canonical map (the caller already sends canonical names).
    workflow_type: ClassVar[str] = ""
    EVENT_MAP: ClassVar[Mapping[str, str]] = {}

    def map_event_name(
        self, raw: dict[str, Any], *, headers: Optional[Mapping[str, str]] = None,  # noqa: ARG002
    ) -> Optional[str]:
        return _event_name(raw)

    def normalize_event(
        self, raw: dict[str, Any], *, headers: Optional[Mapping[str, str]] = None,  # noqa: ARG002
    ) -> CanonicalEventBatch:
        event_name = _event_name(raw) or ""
        recipients = self._recipients(raw)
        ingest_id = raw.get("ingest_id") or raw.get("ingestId")
        return CanonicalEventBatch(
            event_name=event_name,
            recipients=recipients,
            ingest_id=str(ingest_id) if ingest_id else None,
        )

    @staticmethod
    def _recipients(raw: dict[str, Any]) -> list[CanonicalEventRecipient]:
        raw_recipients = raw.get("recipients")
        if isinstance(raw_recipients, list):
            out: list[CanonicalEventRecipient] = []
            for r in raw_recipients:
                if not isinstance(r, dict):
                    continue
                rid = r.get("recipient_id") or r.get("recipientId")
                if rid is None or not str(rid):
                    continue
                payload = r.get("payload")
                if not isinstance(payload, dict):
                    payload = {
                        k: v for k, v in r.items()
                        if k not in ("recipient_id", "recipientId", "payload")
                    }
                out.append(CanonicalEventRecipient(recipient_id=str(rid), payload=payload))
            return out
        rid = raw.get("recipient_id") or raw.get("recipientId")
        if rid is not None and str(rid):
            return [CanonicalEventRecipient(recipient_id=str(rid), payload=dict(raw))]
        return []

    def verify_signature(self, raw: bytes, headers: Mapping[str, str]) -> bool:  # noqa: ARG002
        # Identity source: the per-trigger URL token gates the route.
        return True


from app.services.orchestration.adapters import register_adapter  # noqa: E402

register_adapter(
    capability="event_source", vendor="webhook", adapter=WebhookEventSourceAdapter(),
)

__all__ = ["WebhookEventSourceAdapter"]
