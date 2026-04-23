"""Substitute manifest-derived vocabulary + pack-owned metadata into tool specs.

Tools (see the concrete capability packs) can embed the tokens:

- ``{{catalog_tables}}`` — comma-separated declared catalog table names
- ``{{surface_keys}}``   — comma-separated declared data-surface keys
- ``{{output_schema}}`` — one line per output field, in schema declaration order
- ``{{reason_codes}}`` — comma-separated stable list of the tool's pack-owned codes
- ``{{chart_capabilities}}`` — analytics-only; generated from the deterministic picker
- ``{{limitations}}`` — explicit pack-owned limits/preconditions in stable list order

Substitution is a single deterministic pass (§6.3.1 rule 2). No loops,
conditionals, or pack-crossing reads happen here.
"""

from __future__ import annotations

import copy
from typing import Any, Sequence, TYPE_CHECKING

from pydantic import BaseModel

from app.services.chat_engine.manifest import get_manifest

if TYPE_CHECKING:
    from app.services.chat_engine.capability_pack import CapabilityPack


# ---------------------------------------------------------------------------
# Token generators
# ---------------------------------------------------------------------------


def _format_output_schema(model: type[BaseModel] | None) -> str:
    if model is None:
        return 'Output: (untyped).'
    lines: list[str] = ['Output fields:']
    for field_name, field in model.model_fields.items():
        annotation = field.annotation
        type_str = _format_type(annotation)
        lines.append(f'- {field_name}: {type_str}')
    return '\n'.join(lines)


def _format_type(annotation: Any) -> str:
    if annotation is None:
        return 'any'
    origin = getattr(annotation, '__origin__', None)
    if origin is None:
        return getattr(annotation, '__name__', str(annotation))
    args = getattr(annotation, '__args__', ())
    if not args:
        return getattr(origin, '__name__', str(origin))
    return f"{getattr(origin, '__name__', 'type')}[{', '.join(_format_type(a) for a in args)}]"


def _format_reason_codes(codes: Sequence[str]) -> str:
    if not codes:
        return 'Reason codes: (none).'
    return 'Reason codes: ' + ', '.join(sorted(set(codes))) + '.'


def _format_limitations(limits: Sequence[str]) -> str:
    if not limits:
        return 'Limitations: none.'
    return 'Limitations:\n' + '\n'.join(f'- {limit}' for limit in limits)


def _format_chart_capabilities() -> str:
    """Generate ``{{chart_capabilities}}`` from the deterministic picker.

    Walks the ``Mark`` literal from ``chart_type_picker`` — the canonical
    list of marks the backend can emit. Analytics-only; other packs
    return this string for no tool so it never appears in their specs.
    """
    from typing import get_args

    from app.services.chat_engine.chart_type_picker import Mark

    marks = get_args(Mark)
    return (
        'Chart capabilities: the deterministic chart picker can emit one of '
        + ', '.join(sorted(marks))
        + ' (or no chart when the chartability gate rejects the result set). '
        + 'If a prior chart request came back empty because of an inferred filter, rerun data_query with a clarified or relaxed question instead of answering from the empty slice.'
    )


# ---------------------------------------------------------------------------
# Manifest-token substitution
# ---------------------------------------------------------------------------


def _substitute_manifest(text: str, *, catalog_tables: str, surface_keys: str) -> str:
    return (
        text
        .replace("{{catalog_tables}}", catalog_tables)
        .replace("{{surface_keys}}", surface_keys)
    )


def fill_tool_description(
    tool_spec: dict[str, Any],
    *,
    app_id: str,
    pack: 'CapabilityPack',
) -> dict[str, Any]:
    """Return a deep copy of ``tool_spec`` with every supported token substituted.

    The owning ``pack`` is required — it supplies the
    ``{{output_schema}}``, ``{{reason_codes}}``, and ``{{limitations}}``
    deterministic strings. Manifest tokens (``{{catalog_tables}}``,
    ``{{surface_keys}}``) come from the app manifest.
    """
    manifest = get_manifest(app_id)
    catalog_tables = ', '.join(sorted(manifest.catalog_tables.keys()))
    surface_keys = ', '.join(s.key for s in manifest.data_surfaces)

    filled = copy.deepcopy(tool_spec)
    tool_name = filled.get('name', '')

    output_model = getattr(pack, 'output_schema', lambda _n: None)(tool_name)
    output_schema_str = _format_output_schema(output_model)
    reason_codes_str = _format_reason_codes(
        getattr(pack, 'tool_reason_codes', lambda _n: ())(tool_name),
    )
    limitations_str = _format_limitations(
        getattr(pack, 'tool_limitations', lambda _n: ())(tool_name),
    )
    chart_capabilities_str = _format_chart_capabilities()

    def _apply(text: str) -> str:
        t = _substitute_manifest(
            text,
            catalog_tables=catalog_tables,
            surface_keys=surface_keys,
        )
        return (
            t
            .replace('{{output_schema}}', output_schema_str)
            .replace('{{reason_codes}}', reason_codes_str)
            .replace('{{chart_capabilities}}', chart_capabilities_str)
            .replace('{{limitations}}', limitations_str)
        )

    if isinstance(filled.get('description'), str):
        filled['description'] = _apply(filled['description'])
    props = filled.get('inputSchema', {}).get('properties', {})
    for prop in props.values():
        if isinstance(prop, dict) and isinstance(prop.get('description'), str):
            prop['description'] = _apply(prop['description'])
    return filled


def render_pack_tool_descriptions(
    pack: 'CapabilityPack',
    *,
    app_id: str,
) -> dict[str, str]:
    """Render the pack's tool descriptions into plain strings.

    Honours §6.3.1 rule 5 — the filled description is a deploy-time
    artifact: stable for a running process, never varied per turn or
    per user. Memoization of the full resolved spec list lives in
    ``tool_definitions.resolve_tools``.
    """

    out: dict[str, str] = {}
    for spec in pack.tool_specs():
        filled = fill_tool_description(dict(spec), app_id=app_id, pack=pack)
        out[str(spec.get('name', ''))] = str(filled.get('description', ''))
    return out
