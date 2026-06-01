"""Cat-A picker resolution for the wati_template_picker field.

`match_template` matches a free-text intent against the WATI template list
(the items `list_connection_wati_templates` returns) using stdlib difflib.
It NEVER passes an unmatched intent through as a template name: an unknown
intent resolves to `not_found` so the handler asks the user instead of
writing an invented WhatsApp template name into the canvas.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Literal


# Cutoff for difflib close-match acceptance; below this an intent is unknown.
_CLOSE_CUTOFF = 0.6


@dataclass(frozen=True)
class TemplateMatch:
    """Outcome of matching an intent against the template list.

    `resolved`: name + placeholders are populated. `pick`: candidates holds
    the close template names (name stays None — never pre-pick). `not_found`:
    nothing matched (name None, placeholders empty) — the handler asks.
    """

    status: Literal["resolved", "pick", "not_found"]
    name: str | None = None
    placeholders: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)


def _placeholders_for(template: dict[str, Any]) -> list[str]:
    """Placeholders for a normalised WATI template.

    `parameters` is WATI's source of truth (from customParams via
    wati.extract_variables); fall back to extracting from the candidate only
    when the normalised list is absent.
    """
    params = template.get("parameters")
    if isinstance(params, list):
        return [str(p) for p in params]
    from app.services.orchestration.adapters.wati import extract_variables
    return list(extract_variables(template).variables)


def match_template(*, templates: list[dict[str, Any]], intent: str) -> TemplateMatch:
    """Resolve a free-text intent to exactly one template, a pick list, or not_found."""
    intent_norm = (intent or "").strip()
    names = [str(t.get("name") or "") for t in templates if t.get("name")]
    if not intent_norm or not names:
        return TemplateMatch(status="not_found")

    by_name = {str(t.get("name")): t for t in templates if t.get("name")}

    # Exact, case-insensitive.
    for name in names:
        if name.lower() == intent_norm.lower():
            return TemplateMatch(
                status="resolved",
                name=name,
                placeholders=_placeholders_for(by_name[name]),
            )

    close = difflib.get_close_matches(
        intent_norm, names, n=len(names), cutoff=_CLOSE_CUTOFF,
    )
    if len(close) == 1:
        name = close[0]
        return TemplateMatch(
            status="resolved",
            name=name,
            placeholders=_placeholders_for(by_name[name]),
        )
    if len(close) > 1:
        return TemplateMatch(status="pick", candidates=close)
    return TemplateMatch(status="not_found")


__all__ = ["TemplateMatch", "match_template"]
