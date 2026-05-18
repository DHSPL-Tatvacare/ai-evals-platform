"""Capability adapter Protocols — messaging (WhatsApp et al.) and voice."""
from __future__ import annotations

from typing import Any, ClassVar, Mapping, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orchestration.adapters.canonical import (
    CanonicalMessagingEvent,
    CanonicalSendRequest,
    CanonicalSendResponse,
    CanonicalVoiceEvent,
    CanonicalVoiceRequest,
    CanonicalVoiceResponse,
)


class MessagingAdapter(Protocol):
    capability: ClassVar[str]
    vendor: ClassVar[str]

    async def send_template(
        self, *, connection: Any, request: CanonicalSendRequest,
    ) -> CanonicalSendResponse: ...

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


class VoiceAdapter(Protocol):
    capability: ClassVar[str]
    vendor: ClassVar[str]

    async def place_call(
        self, *, connection: Any, request: CanonicalVoiceRequest,
    ) -> CanonicalVoiceResponse: ...

    def normalize_webhook(self, raw: dict[str, Any]) -> CanonicalVoiceEvent: ...

    def verify_signature(self, raw: bytes, headers: Mapping[str, str]) -> bool: ...

    async def handle_webhook(
        self,
        db: AsyncSession,
        *,
        tenant_id: Any,
        app_id: str,
        payload: dict[str, Any],
    ) -> None: ...
