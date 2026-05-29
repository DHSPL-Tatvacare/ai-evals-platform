"""Capability-named adapter registry; vendor lives in the ProviderConnection row."""
from __future__ import annotations

from typing import Any

from app.services.orchestration.adapters.canonical import (
    CanonicalEventBatch,
    CanonicalEventRecipient,
    CanonicalMessagingEvent,
    CanonicalSendRequest,
    CanonicalSendResponse,
    CanonicalVoiceEvent,
    CanonicalVoiceRequest,
    CanonicalVoiceResponse,
    VariableSurface,
)
from app.services.orchestration.adapters.protocol import (
    EventSourceAdapter,
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


def registered_adapter_instances() -> list[Any]:
    """Registered adapter instances; consumers introspect them without the registry dict."""
    return list(_REGISTRY.values())


def capability_for_vendor(vendor: str) -> str | None:
    """Reverse lookup — None when no adapter is registered for this vendor."""
    for cap, vnd in _REGISTRY.keys():
        if vnd == vendor:
            return cap
    return None


__all__ = [
    "AdapterNotRegisteredError",
    "CanonicalEventBatch",
    "CanonicalEventRecipient",
    "CanonicalMessagingEvent",
    "CanonicalSendRequest",
    "CanonicalSendResponse",
    "CanonicalVoiceEvent",
    "CanonicalVoiceRequest",
    "CanonicalVoiceResponse",
    "EventSourceAdapter",
    "MessagingAdapter",
    "VariableSurface",
    "VoiceAdapter",
    "capability_for_vendor",
    "register_adapter",
    "registered_adapter_instances",
    "registered_adapters",
    "resolve_adapter",
]


# Import vendor modules for their registration side effects so EVERY entrypoint
# (backend, worker, tests) that touches the adapters package gets the full
# registry — not just the backend lifespan. Kept last: register_adapter must be
# defined before these run, and the submodules only import that symbol back.
from app.services.orchestration.adapters import aisensy as _aisensy  # noqa: E402,F401
from app.services.orchestration.adapters import bolna as _bolna  # noqa: E402,F401
from app.services.orchestration.adapters import wati as _wati  # noqa: E402,F401
from app.services.orchestration.adapters.event_source import frappe as _es_frappe  # noqa: E402,F401
from app.services.orchestration.adapters.event_source import lsq as _es_lsq  # noqa: E402,F401
from app.services.orchestration.adapters.event_source import mytatva as _es_mytatva  # noqa: E402,F401
from app.services.orchestration.adapters.event_source import webhook as _es_webhook  # noqa: E402,F401
