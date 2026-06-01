"""Capability adapter Protocols — messaging (WhatsApp et al.) and voice."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orchestration.adapters.canonical import (
    CancelDispatchResult,
    CanonicalEventBatch,
    CanonicalMessagingEvent,
    CanonicalSendRequest,
    CanonicalSendResponse,
    CanonicalVoiceEvent,
    CanonicalVoiceRequest,
    CanonicalVoiceResponse,
)
from app.services.orchestration.analytics.outcomes import EngagementBucket


@dataclass(frozen=True)
class FunnelStage:
    key: str
    label: str


class MessagingAdapter(Protocol):
    capability: ClassVar[str]
    vendor: ClassVar[str]
    ACTION_OUTCOME_MAP: ClassVar[dict[str, EngagementBucket]]

    async def send_template(
        self, *, connection: Any, request: CanonicalSendRequest,
    ) -> CanonicalSendResponse: ...

    # READ — authoring lists approved templates for this connection; never mutates.
    async def list_templates(self, connection: dict[str, Any]) -> list[dict[str, Any]]: ...

    def normalize_webhook(self, raw: dict[str, Any]) -> CanonicalMessagingEvent: ...

    def verify_signature(self, raw: bytes, headers: Mapping[str, str]) -> bool: ...

    async def handle_webhook(
        self,
        db: AsyncSession,
        *,
        tenant_id: Any,
        app_id: str,
        payload: dict[str, Any],
    ) -> None: ...

    async def cancel_dispatch(
        self, *, connection: Any, action: Any,
    ) -> CancelDispatchResult: ...

    async def cancel_run_actions(
        self, *, connection: Any, actions: list[Any],
    ) -> list[CancelDispatchResult]: ...

    def outcome_bucket(self, action_type: str) -> EngagementBucket:
        """Map a terminal child action_type to a channel-agnostic engagement bucket."""
        ...

    def funnel_stages(self) -> list["FunnelStage"]:
        """Ordered engagement funnel stages for this capability."""
        ...


class EventSourceAdapter(Protocol):
    """Maps a native CRM/clinical webhook payload to canonical event(s).

    ``EVENT_MAP`` is a declarative dict (native key -> canonical event name);
    ``normalize_event`` is the coded payload reshape into recipients.
    """
    capability: ClassVar[str]
    vendor: ClassVar[str]
    workflow_type: ClassVar[str]
    EVENT_MAP: ClassVar[Mapping[str, str]]

    def map_event_name(
        self, raw: dict[str, Any], *, headers: Optional[Mapping[str, str]] = None,
    ) -> Optional[str]: ...

    def normalize_event(
        self, raw: dict[str, Any], *, headers: Optional[Mapping[str, str]] = None,
    ) -> CanonicalEventBatch: ...

    def verify_signature(self, raw: bytes, headers: Mapping[str, str]) -> bool: ...


class VoiceAdapter(Protocol):
    capability: ClassVar[str]
    vendor: ClassVar[str]
    ACTION_OUTCOME_MAP: ClassVar[dict[str, EngagementBucket]]
    # None means "vendor never batches"; integer is the cohort size at
    # or above which the node flips from per-recipient ``place_call`` to
    # a single ``place_call_batch`` upload.
    batch_threshold: ClassVar[Optional[int]]

    async def place_call(
        self, *, connection: Any, request: CanonicalVoiceRequest,
    ) -> CanonicalVoiceResponse: ...

    async def place_call_batch(
        self,
        *,
        connection: Any,
        requests: list[CanonicalVoiceRequest],
        recipient_ids: list[str],
    ) -> list[CanonicalVoiceResponse]: ...

    def normalize_webhook(self, raw: dict[str, Any]) -> CanonicalVoiceEvent: ...

    def verify_signature(self, raw: bytes, headers: Mapping[str, str]) -> bool: ...

    def is_terminal(self, status: Optional[str]) -> bool: ...

    async def fetch_execution(
        self, *, connection: Any, execution_id: str,
    ) -> Optional[dict[str, Any]]: ...

    async def fetch_batch_summary(
        self, *, connection: Any, batch_id: str,
    ) -> Optional[dict[str, Any]]: ...

    async def fetch_batch_executions(
        self, *, connection: Any, batch_id: str,
        page_number: int = 1, page_size: int = 50,
    ) -> dict[str, Any]: ...

    async def handle_webhook(
        self,
        db: AsyncSession,
        *,
        tenant_id: Any,
        app_id: str,
        payload: dict[str, Any],
    ) -> None: ...

    async def cancel_dispatch(
        self, *, connection: Any, action: Any,
    ) -> CancelDispatchResult: ...

    async def cancel_batch(
        self, *, connection: Any, batch_id: str,
    ) -> CancelDispatchResult: ...

    async def cancel_run_actions(
        self, *, connection: Any, actions: list[Any],
    ) -> list[CancelDispatchResult]: ...

    def outcome_bucket(self, action_type: str) -> EngagementBucket:
        """Map a terminal child action_type to a channel-agnostic engagement bucket."""
        ...

    def funnel_stages(self) -> list["FunnelStage"]:
        """Ordered engagement funnel stages for this capability."""
        ...
