"""Match template placeholders to cohort fields (Task #7, cat-C).

Pure, DB-free matcher used by the ``map_template_variables`` authoring tool.
Binds each template placeholder to a cohort field by exact → normalized
(lower/strip/underscore) → difflib close match, producing VariableMappingRow-
shaped dicts. Placeholders with no confident field land in ``unmatched`` so the
agent ASKS rather than binding a guess. ``payload_fields_to_add`` is exactly the
set of matched fields, for back-propagation onto source.cohort.payload_fields.
"""
from __future__ import annotations

import difflib
from typing import TypedDict

# difflib cutoff for a confident fuzzy bind; below this the placeholder is
# treated as unmatched and surfaced for the agent to ask about.
_FUZZY_CUTOFF = 0.82


class VariableMapping(TypedDict):
    mappings: list[dict]
    payload_fields_to_add: list[str]
    unmatched: list[str]


def _normalize(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _match_field(placeholder: str, fields: list[str], norm_fields: dict[str, str]) -> str | None:
    """Resolve one placeholder to a field via exact → normalized → fuzzy."""
    if placeholder in fields:
        return placeholder
    norm = _normalize(placeholder)
    if norm in norm_fields:
        return norm_fields[norm]
    close = difflib.get_close_matches(norm, list(norm_fields), n=1, cutoff=_FUZZY_CUTOFF)
    if close:
        return norm_fields[close[0]]
    return None


def map_variables(*, placeholders: list[str], fields: list[str]) -> VariableMapping:
    """Bind placeholders to cohort fields; never bind a guess.

    Returns VariableMappingRow-shaped payload mappings for confident matches,
    the de-duplicated set of matched fields to add to the upstream source's
    payload_fields, and the unmatched placeholders for the agent to ask about.
    """
    # First-normalization wins so an exact-cased field is preferred on collision.
    norm_fields: dict[str, str] = {}
    for field in fields:
        norm_fields.setdefault(_normalize(field), field)

    mappings: list[dict] = []
    matched_fields: list[str] = []
    unmatched: list[str] = []

    for placeholder in placeholders:
        field = _match_field(placeholder, fields, norm_fields)
        if field is None:
            unmatched.append(placeholder)
            continue
        mappings.append({
            "agent_variable": placeholder,
            "source_kind": "payload",
            "payload_field": field,
        })
        if field not in matched_fields:
            matched_fields.append(field)

    return VariableMapping(
        mappings=mappings,
        payload_fields_to_add=matched_fields,
        unmatched=unmatched,
    )


__all__ = ["VariableMapping", "map_variables"]
