"""Shared SAFE tool-output matcher for specialist RunResult extraction.

Agents-SDK reality: a ``tool_call_output_item.raw_item`` carries
``call_id`` (not ``name``); the tool name lives on the preceding
``tool_call_item``. Build a ``call_id -> tool_name`` index from the run's
tool_call_items, then match outputs against a tool name via that index.

SAFE by construction: any output whose call_id is not in the index, or
maps to a different name, returns ``False`` — no "assume the only tool"
catch-all. Every specialist (single- or multi-tool) shares this.
"""
from __future__ import annotations

from typing import Any


def build_call_name_index(new_items: list[Any]) -> dict[str, str]:
    """call_id -> tool_name, harvested from every tool_call_item in the run."""
    index: dict[str, str] = {}
    for item in new_items:
        if getattr(item, 'type', None) != 'tool_call_item':
            continue
        raw = getattr(item, 'raw_item', None)
        call_id = (
            raw.get('call_id') if isinstance(raw, dict)
            else getattr(raw, 'call_id', None)
        )
        name = (
            raw.get('name') if isinstance(raw, dict)
            else getattr(raw, 'name', None)
        )
        if isinstance(call_id, str) and isinstance(name, str):
            index[call_id] = name
    return index


def is_tool_output_for(
    item: Any,
    tool_name: str,
    *,
    call_name_index: dict[str, str],
) -> bool:
    """True iff `item` is a tool_call_output_item whose call_id maps to `tool_name`."""
    if getattr(item, 'type', None) != 'tool_call_output_item':
        return False
    raw = getattr(item, 'raw_item', None)
    call_id = (
        raw.get('call_id') if isinstance(raw, dict)
        else getattr(raw, 'call_id', None)
    )
    if not isinstance(call_id, str):
        return False
    return call_name_index.get(call_id) == tool_name
