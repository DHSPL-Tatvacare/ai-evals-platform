"""Variable-mapping precedence + fallback (Phase 10 commit 2).

Pure functions consumed by ``crm.send_wati`` and ``crm.place_bolna_call`` to
build provider call payloads from recipient data.

Precedence:

1. **Node-level ``variable_mappings``** (when non-empty) override the
   template's ``parameter_map`` / ``user_data_map``. Each row binds an
   ``agent_variable`` to either a recipient payload field
   (``source_kind='payload'``) or a static literal
   (``source_kind='static'``).
2. **Template fallback** — when ``variable_mappings`` is empty / absent,
   we project the template's ``parameter_map`` / ``user_data_map`` shape
   into the same output. This keeps seeded workflows that haven't been
   re-saved through the new builder running unchanged.

A missing payload field resolves to ``""`` (matches existing handler
behaviour). Unknown ``source_kind`` raises ``VariableMappingConfigError``
so workflow-config drift surfaces as a node-step failure rather than a
silent empty payload.
"""
from __future__ import annotations

from typing import Any


class VariableMappingConfigError(ValueError):
    """Raised when a variable_mapping row carries an unsupported source_kind."""


def _resolve_one(
    mapping: dict[str, Any], payload: dict[str, Any],
) -> tuple[str, str]:
    name = mapping.get("agent_variable") or ""
    if not name:
        raise VariableMappingConfigError(
            "variable_mapping row missing 'agent_variable'"
        )
    kind = mapping.get("source_kind", "payload")
    if kind == "payload":
        field = mapping.get("payload_field") or ""
        raw = payload.get(field) if field else None
        return name, "" if raw is None else str(raw)
    if kind == "static":
        raw = mapping.get("static_value")
        return name, "" if raw is None else str(raw)
    raise VariableMappingConfigError(
        f"variable_mapping row {name!r} has unsupported source_kind={kind!r}"
    )


def apply_variable_mappings_dict(
    mappings: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    template_fallback: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    """Build a ``dict[name, value]`` for Bolna's ``user_data``.

    When ``mappings`` is empty we fall back to ``template_fallback`` (the
    legacy template-level ``user_data_map``). The fallback rows have shape
    ``[{name, source}]`` where ``source`` is a recipient payload field —
    same semantics as the pre-Phase-10 handler.
    """
    if mappings:
        out: dict[str, str] = {}
        for row in mappings:
            name, value = _resolve_one(row, payload)
            out[name] = value
        return out
    out = {}
    for entry in template_fallback or []:
        src = entry.get("source", "")
        out[entry["name"]] = "" if not src else str(payload.get(src, "") or "")
    return out


def apply_variable_mappings_list(
    mappings: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    template_fallback: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build a ``[{name, value}, ...]`` list for WATI's ``parameters``.

    Order is preserved: node-level mappings keep their declared order;
    fallback rows preserve the template's declared order.
    """
    if mappings:
        out: list[dict[str, str]] = []
        for row in mappings:
            name, value = _resolve_one(row, payload)
            out.append({"name": name, "value": value})
        return out
    out_list: list[dict[str, str]] = []
    for entry in template_fallback or []:
        src = entry.get("source")
        val = payload.get(src) if src else None
        out_list.append(
            {"name": entry["name"], "value": "" if val is None else str(val)}
        )
    return out_list


__all__ = [
    "VariableMappingConfigError",
    "apply_variable_mappings_dict",
    "apply_variable_mappings_list",
]
