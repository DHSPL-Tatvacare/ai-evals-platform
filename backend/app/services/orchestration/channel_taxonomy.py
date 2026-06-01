"""Channel taxonomy DERIVED from dispatch-node declarations — no hardcoded {channel: providers} table.

Providers come from each dispatch node's ``connection_id`` field ``x-providers`` declaration.
The channel label is the node's own runtime ``channel="..."`` literal passed to ``ActionDispatch`` —
the platform-canonical channel string comm-cap and cross-channel reporting already key on — read
statically via AST from the node's defining module, never restated here.
"""
from __future__ import annotations

import ast
import importlib
import inspect
from typing import Any, Optional

from app.services.orchestration.node_registry import NODE_REGISTRY


def _x_providers_from_schema(config_schema: type) -> Optional[list[str]]:
    """Pull x-providers off whichever field declares it in the node's config schema."""
    schema = config_schema.model_json_schema()
    for spec in schema.get("properties", {}).values():
        if isinstance(spec, dict) and isinstance(spec.get("x-providers"), list):
            return [str(p) for p in spec["x-providers"]]
    return None


def _declared_channel_literal(handler: Any) -> Optional[str]:
    """The node's own ``channel="..."`` keyword literal — the canonical channel string it dispatches on."""
    module = importlib.import_module(type(handler).__module__)
    try:
        tree = ast.parse(inspect.getsource(module))
    except OSError:
        return None
    literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "channel" and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                literals.add(node.value.value)
    # A dispatch node declares exactly one canonical channel; ambiguity is not a taxonomy.
    return literals.pop() if len(literals) == 1 else None


def channel_provider_map() -> dict[str, list[str]]:
    """{channel: sorted(providers)} derived by scanning the node registry for x-providers + the channel literal."""
    # Force @register_node side-effects; the registry is empty unless the node package was imported.
    importlib.import_module("app.services.orchestration.nodes")
    out: dict[str, set[str]] = {}
    for (_wf, _node_type), handler in NODE_REGISTRY.items():
        providers = _x_providers_from_schema(handler.config_schema)
        if not providers:
            continue
        channel = _declared_channel_literal(handler)
        if channel is None:
            continue
        out.setdefault(channel, set()).update(providers)
    if not out:
        # A dropped node import would silently degrade resolve_channel to None for valid channels; fail loud.
        raise RuntimeError("channel taxonomy empty: no dispatch nodes registered x-providers")
    return {channel: sorted(providers) for channel, providers in out.items()}


# Aliases are inherently lexical — the only literal allowed; maps user phrasings to canonical channels.
_CHANNEL_ALIASES: dict[str, str] = {
    "whatsapp": "whatsapp",
    "whatsapp message": "whatsapp",
    "wa": "whatsapp",
    "whatsapp template": "whatsapp",
    "message": "whatsapp",
    "voice": "voice",
    "call": "voice",
    "phone": "voice",
    "phone call": "voice",
    "voice call": "voice",
}


def resolve_channel(text: str) -> Optional[str]:
    """Normalize a free-text hint to a canonical channel that exists in the derived map, else None."""
    if not text:
        return None
    canonical = _CHANNEL_ALIASES.get(text.strip().lower())
    if canonical is None:
        return None
    return canonical if canonical in channel_provider_map() else None


__all__ = ["channel_provider_map", "resolve_channel"]
