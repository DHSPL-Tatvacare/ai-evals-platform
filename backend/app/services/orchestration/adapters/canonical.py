"""Canonical (vendor-agnostic) request, response, and event shapes for capability adapters.

Every dispatch action MUST carry ``contact`` and ``provider_correlation_id`` per the
CLAUDE.md invariant; both fields are required on the canonical response and event types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional

from app.services.orchestration.analytics.outcomes import EngagementBucket  # noqa: F401  re-export: single import site


@dataclass(frozen=True)
class VariableSurface:
    """A provider entity's variable surface — the variables it exposes plus any
    previewable text. Each adapter exposes ``extract_variables(raw) -> VariableSurface``
    (deriving variables its own way); the agent-variables endpoint splats this into
    one cross-provider response shape. Fields a provider doesn't have stay empty.
    """
    variables: list[str] = field(default_factory=list)
    prompt: str = ""
    welcome_message: str = ""
    body: str = ""
    body_original: Optional[str] = None


@dataclass(frozen=True)
class CanonicalSendRequest:
    contact: str
    template_name: str
    broadcast_name: str = ""
    channel_number: str = ""
    variables: dict[str, str] = field(default_factory=dict)
    reply_context_id: Optional[str] = None


@dataclass(frozen=True)
class CanonicalSendResponse:
    provider_correlation_id: str
    contact: str
    # Send-truth: a provider HTTP 200 is not delivery. ``accepted`` is the parsed
    # body verdict (all vendors); ``reason`` carries why a 200 was a non-send.
    accepted: bool = True
    reason: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalMessagingEvent:
    status: str
    contact: str
    provider_correlation_id: str
    reply_context_id: Optional[str] = None
    reply_type: Optional[str] = None
    reply_text: Optional[str] = None
    button_id: Optional[str] = None
    list_id: Optional[str] = None
    vendor_raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalVoiceRequest:
    contact: str
    agent_id: str
    variables: dict[str, str] = field(default_factory=dict)
    from_phone: Optional[str] = None
    bypass_call_guardrails: bool = False


@dataclass(frozen=True)
class CanonicalVoiceResponse:
    provider_correlation_id: str
    contact: str
    mode: str
    # Same send-truth verdict as messaging (one shape, all vendors).
    accepted: bool = True
    reason: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalVoiceEvent:
    outcome: str
    contact: str
    provider_correlation_id: str
    duration_sec: Optional[int] = None
    transcript: Optional[str] = None
    recording_url: Optional[str] = None
    vendor_raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalEventRecipient:
    recipient_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalEventBatch:
    """Vendor-agnostic inbound event — one canonical event name, one or more recipients.

    ``ingest_id`` is the vendor-stable dedupe key (vendor event id, doctype+doc,
    activity id, …). The route combines it with the trigger id to form the
    replay-dedupe idempotency key, so a CRM retry never creates a second run.
    """
    event_name: str
    recipients: list[CanonicalEventRecipient] = field(default_factory=list)
    ingest_id: Optional[str] = None


class CancelDispatchOutcome(StrEnum):
    stopped = "stopped"
    cancelled = "cancelled"
    noop_unsupported = "noop_unsupported"
    noop_already_delivered = "noop_already_delivered"
    noop_already_terminal = "noop_already_terminal"
    provider_error = "provider_error"


@dataclass(frozen=True)
class CancelDispatchResult:
    outcome: CancelDispatchOutcome
    provider_status_code: Optional[int] = None
    provider_message: Optional[str] = None
