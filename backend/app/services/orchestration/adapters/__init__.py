"""Capability-named adapter registry; vendor lives in the ProviderConnection row."""
from __future__ import annotations

from typing import Any

from app.services.orchestration.adapters.canonical import (
    CanonicalMessagingEvent,
    CanonicalSendRequest,
    CanonicalSendResponse,
    CanonicalVoiceEvent,
    CanonicalVoiceRequest,
    CanonicalVoiceResponse,
)
from app.services.orchestration.adapters.protocol import (
    MessagingAdapter,
    VoiceAdapter,
)


class AdapterNotRegisteredError(LookupError):
    pass


_REGISTRY: dict[tuple[str, str], Any] = {}


def register_adapter(*, capability: str, vendor: str, adapter: Any) -> None:
    key = (capability, vendor)
    if key in _REGISTRY:
        raise RuntimeError(f"adapter already registered for {key}")
    _REGISTRY[key] = adapter


def resolve_adapter(*, capability: str, vendor: str) -> Any:
    try:
        return _REGISTRY[(capability, vendor)]
    except KeyError as exc:
        raise AdapterNotRegisteredError(
            f"no adapter registered for capability={capability!r} vendor={vendor!r}",
        ) from exc


def registered_adapters() -> list[tuple[str, str]]:
    return sorted(_REGISTRY.keys())


__all__ = [
    "AdapterNotRegisteredError",
    "CanonicalMessagingEvent",
    "CanonicalSendRequest",
    "CanonicalSendResponse",
    "CanonicalVoiceEvent",
    "CanonicalVoiceRequest",
    "CanonicalVoiceResponse",
    "MessagingAdapter",
    "VoiceAdapter",
    "register_adapter",
    "registered_adapters",
    "resolve_adapter",
]
