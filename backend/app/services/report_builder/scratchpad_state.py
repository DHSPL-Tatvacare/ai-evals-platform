"""Helpers for durable Sherlock scratchpad state."""
from __future__ import annotations

import json
import re
from typing import Any

_MAX_ANALYSIS_COLUMNS = 8
_MAX_ANALYSIS_PREVIEW_ROWS = 3
_TEMPORAL_NAME_PATTERN = re.compile(
    r'(date|time|month|week|year|quarter|day|period|created|updated)',
    re.IGNORECASE,
)
_ISO_DATE_PATTERN = re.compile(
    r'^\d{4}[-/]\d{2}([-/]\d{2})?([T ]\d{2}:\d{2}(:\d{2})?)?',
)

# M2: typed provenance labels (plan §8.1). Callers that write to
# ``resolved_entities`` / ``active_filters`` pass a provenance label
# describing where the value came from so carry-forward can distinguish
# user-explicit from scope-derived state. The enum lives in
# :mod:`app.services.sherlock.provenance`; this module accepts plain
# strings to keep the scratchpad serializable as JSON.
_VALID_PROVENANCE = frozenset({
    'user_explicit',
    'scope_derived',
    'resolver_derived',
    'model_inferred',
    'heuristic',
})


def default_scratchpad() -> dict[str, Any]:
    # Audit fix: ``composed_report`` used to live here as Sherlock-wide
    # runtime state, leaking report-builder domain into the generic
    # scratchpad (plan Phase 1 §485-512 — Sherlock Core is pack-agnostic).
    # Blueprint preview state is now reconstructed from assistant-message
    # ``BlueprintPart`` artifacts on the frontend and from tool-outcome
    # envelopes in message history; Sherlock Core no longer stores it.
    return {
        'findings': [],
        'errors': [],
        'discovery': None,
        'lookups': {},
        'resolved_entities': {},
        'active_filters': {},
        'discovered_schema': {
            'tables_inspected': [],
            'columns_by_table': {},
            'relations_found': [],
            'json_structures': {},
        },
        'last_analysis': None,
        'analysis_history': [],
        'last_evidence': None,
        'last_data_check': None,
        # Phase 2: structured per-tool outcome log (plan §6 step 6).
        # Each entry: {tool, reason_code, artifact_type, counts}.
        'outcomes': [],
        # Phase 1 (generic recovery / state contracts, plan §42-107).
        # Populated by ``apply_state_delta`` when a pack emits
        # ``envelope.state_delta`` / ``envelope.recovery``. Pack-agnostic:
        # any pack may write here, harness merge is deterministic.
        'confirmed_constraints': [],
        'grounded_refs': [],
        'open_threads': [],
        'last_result': None,
        'last_failure': None,
    }


def _serialize_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _ordered_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            key_text = str(key)
            if key_text not in seen:
                seen.add(key_text)
                columns.append(key_text)
    return columns


def _compact_row(row: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    return {
        column: _serialize_scalar(row[column])
        for column in columns[:_MAX_ANALYSIS_COLUMNS]
        if column in row
    }


def _is_numeric_value(value: Any) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False
    return False


def _is_temporal_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_ISO_DATE_PATTERN.match(value.strip()))


def _infer_column_types(
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    dimensions: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    ordered_dimensions = {
        str(dimension.get('name', ''))
        for dimension in (dimensions or [])
        if isinstance(dimension, dict) and dimension.get('ordering')
    }

    inferred: dict[str, str] = {}
    for column in columns:
        if column in ordered_dimensions:
            inferred[column] = 'ordered_categorical'
            continue

        values = [
            row[column]
            for row in rows
            if isinstance(row, dict) and column in row and row[column] is not None
        ]
        if not values:
            inferred[column] = 'categorical'
            continue
        if all(_is_numeric_value(value) for value in values):
            inferred[column] = 'numeric'
            continue
        if _TEMPORAL_NAME_PATTERN.search(column) or all(_is_temporal_value(value) for value in values):
            inferred[column] = 'temporal'
            continue
        inferred[column] = 'categorical'
    return inferred


def build_analysis_snapshot(
    result: dict[str, Any],
    dimensions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = result.get('data', [])
    if not isinstance(rows, list):
        rows = []
    normalized_rows = [row for row in rows if isinstance(row, dict)]
    columns = _ordered_columns(normalized_rows)
    preview_rows = [
        _compact_row(row, columns)
        for row in normalized_rows[:_MAX_ANALYSIS_PREVIEW_ROWS]
    ]
    focus = preview_rows[0] if preview_rows else {}
    row_count = result.get('row_count')
    if not isinstance(row_count, int):
        row_count = len(normalized_rows)

    column_entries = result.get('columns', [])
    columns_metadata = [
        entry
        for entry in column_entries
        if isinstance(entry, dict) and entry.get('name')
    ]
    if columns_metadata:
        columns = [str(entry['name']) for entry in columns_metadata]
        column_types = {}
        for entry in columns_metadata:
            role = str(entry.get('role') or 'dimension')
            if role == 'measure':
                column_types[str(entry['name'])] = 'numeric'
            elif role == 'temporal':
                column_types[str(entry['name'])] = 'temporal'
            elif role == 'ordered_categorical':
                column_types[str(entry['name'])] = 'ordered_categorical'
            else:
                column_types[str(entry['name'])] = 'categorical'
    else:
        column_types = _infer_column_types(columns, normalized_rows, dimensions=dimensions)
        columns_metadata = []

    return {
        'question': str(result.get('question', '')).strip(),
        'row_count': row_count,
        'sql_used': result.get('sql_used'),
        'columns': columns,
        'columns_metadata': columns_metadata,
        'data': normalized_rows,
        'preview_rows': preview_rows,
        'focus': focus,
        'column_types': column_types,
        # Phase 5: kind-discriminated hint for the next turn's scratchpad.
        # ``None`` when the typed contract wasn't produced (e.g. data_check).
        'chart_summary': _chart_summary_from_result(result),
        'warnings': result.get('warnings', []),
        'applied_filters': result.get('applied_filters', {}),
    }


def _chart_summary_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
    """Derive a compact ``{kind, mark?, reason_code?, warning?}`` summary.

    Runs the same chartability gate + chart-type picker used by the live
    chart-payload orchestrator, so the scratchpad hint for the next turn
    matches what the user actually saw. Pure — no LLM, no I/O.
    """
    typed_rows = result.get('data')
    raw_cols = result.get('typed_columns')
    if not isinstance(typed_rows, list) or not isinstance(raw_cols, list):
        return None

    from app.services.chat_engine.chartability_gate import evaluate as evaluate_gate
    from app.services.chat_engine.chart_type_picker import pick as pick_chart
    from app.services.chat_engine.result_set_typer import TypedColumn, TypedResultSet

    columns: list[TypedColumn] = []
    for raw in raw_cols:
        if not isinstance(raw, dict):
            continue
        name = raw.get('name')
        role = raw.get('role')
        data_type = raw.get('data_type')
        if not (name and role and data_type):
            continue
        try:
            columns.append(
                TypedColumn(
                    name=str(name),
                    role=role,
                    data_type=data_type,
                    semantic_type=raw.get('semantic_type'),
                    cardinality=int(raw.get('cardinality') or 0),
                    null_frac=float(raw.get('null_frac') or 0.0),
                    is_constant=bool(raw.get('is_constant') or False),
                )
            )
        except Exception:
            return None
    clean_rows = [r for r in typed_rows if isinstance(r, dict)]
    typed = TypedResultSet(columns=columns, rows=clean_rows)
    gate = evaluate_gate(typed)

    summary: dict[str, Any] = {'kind': _gate_to_kind(gate.fallback)}
    if gate.reason_code:
        summary['reason_code'] = gate.reason_code
    if gate.warning:
        summary['warning'] = gate.warning
    if gate.chartable:
        try:
            picked = pick_chart(typed)
            summary['mark'] = picked.mark
        except ValueError:
            # Picker refused despite gate approval — fall back to table kind
            # so the scratchpad hint matches what the orchestrator will emit.
            from app.services.chat_engine import reason_codes as _rc

            summary['kind'] = 'table'
            summary['reason_code'] = _rc.CG_EMIT_FAILED
    return summary


def _gate_to_kind(fallback: str) -> str:
    if fallback == 'empty':
        return 'empty'
    if fallback == 'kpi':
        return 'kpi'
    if fallback == 'summary':
        return 'summary'
    if fallback == 'table':
        return 'table'
    # 'chart' or 'chart_with_warning'
    return 'chart'


def push_analysis_snapshot(scratchpad: dict[str, Any], snapshot: dict[str, Any], *, max_entries: int = 5) -> None:
    history = scratchpad.setdefault('analysis_history', [])
    if not isinstance(history, list):
        history = []
    history.append(snapshot)
    scratchpad['analysis_history'] = history[-max_entries:]
    scratchpad['last_analysis'] = snapshot


def _coerce_provenance(value: str | None) -> str:
    normalized = str(value or 'model_inferred').strip().lower()
    if normalized not in _VALID_PROVENANCE:
        return 'model_inferred'
    return normalized


def remember_resolved_entities(
    scratchpad: dict[str, Any],
    *,
    entity_type: str,
    search: str,
    matches: list[dict[str, Any]],
    provenance: str | None = None,
    source_tool: str | None = None,
    source_turn_id: str | None = None,
) -> None:
    """Persist a resolved-entity record with provenance typing.

    M2 (plan §8.1): every entry carries ``provenance`` so carry-forward
    can drop ``scope_derived`` values on scope change and keep
    ``user_explicit`` / ``resolver_derived`` values sticky. Default is
    ``model_inferred`` when the caller does not declare — the lowest
    trust tier that still records the value.
    """
    resolved_entities = scratchpad.setdefault('resolved_entities', {})
    if not isinstance(resolved_entities, dict):
        resolved_entities = {}
    resolved_entities[entity_type] = {
        'search': search,
        'matches': matches[:10],
        'provenance': _coerce_provenance(provenance),
        'source_tool': source_tool,
        'source_turn_id': source_turn_id,
    }
    scratchpad['resolved_entities'] = resolved_entities


def remember_last_evidence(
    scratchpad: dict[str, Any],
    *,
    surface_key: str,
    record_count: int,
    entity_type: str | None,
    entity_value: str | None,
) -> None:
    scratchpad['last_evidence'] = {
        'surface_key': surface_key,
        'record_count': record_count,
        'entity_type': entity_type,
        'entity_value': entity_value,
    }


def remember_active_filters(
    scratchpad: dict[str, Any],
    filters: dict[str, Any] | None,
    *,
    provenance: str | None = None,
    source_tool: str | None = None,
    source_turn_id: str | None = None,
) -> None:
    """Persist active filters with provenance typing (plan §8.1).

    The map value is still the compact filter-shape other code reads,
    but now wrapped:
    ``{'value': <original>, 'provenance': 'user_explicit' | ...,
       'source_tool': ..., 'source_turn_id': ...}``.
    ``copy_filters`` keeps the original shape inside ``value`` so
    read-side consumers that accepted the old plain-value shape still
    work — they just need to unwrap.
    """
    copied = copy_filters(filters)
    prov = _coerce_provenance(provenance)
    wrapped: dict[str, Any] = {}
    for key, original in copied.items():
        wrapped[key] = {
            'value': original,
            'provenance': prov,
            'source_tool': source_tool,
            'source_turn_id': source_turn_id,
        }
    scratchpad['active_filters'] = wrapped


def active_filter_values(scratchpad: dict[str, Any] | None) -> dict[str, Any]:
    """Unwrap ``active_filters`` into the plain ``{key: value}`` shape.

    Read-side compat helper: most consumers care about the filter value,
    not the provenance; this hides the per-entry metadata without
    dropping it.
    """
    if not isinstance(scratchpad, dict):
        return {}
    filters = scratchpad.get('active_filters')
    if not isinstance(filters, dict):
        return {}
    out: dict[str, Any] = {}
    for key, entry in filters.items():
        if isinstance(entry, dict) and 'value' in entry and 'provenance' in entry:
            out[key] = entry['value']
        else:
            out[key] = entry
    return out


def active_filter_provenance(scratchpad: dict[str, Any] | None) -> dict[str, str]:
    """Return ``{key: provenance}`` for every entry in ``active_filters``."""
    if not isinstance(scratchpad, dict):
        return {}
    filters = scratchpad.get('active_filters')
    if not isinstance(filters, dict):
        return {}
    out: dict[str, str] = {}
    for key, entry in filters.items():
        if isinstance(entry, dict) and isinstance(entry.get('provenance'), str):
            out[key] = entry['provenance']
    return out


def drop_scope_derived_filters(scratchpad: dict[str, Any] | None) -> None:
    """Drop ``active_filters`` entries whose provenance is ``scope_derived``.

    Called on scope change (plan §8.1 carry-forward policy): user-stated
    filters are sticky across scope moves, but scope-derived residue
    must not survive.
    """
    if not isinstance(scratchpad, dict):
        return
    filters = scratchpad.get('active_filters')
    if not isinstance(filters, dict):
        return
    kept: dict[str, Any] = {}
    for key, entry in filters.items():
        prov = None
        if isinstance(entry, dict):
            prov = entry.get('provenance')
        if prov == 'scope_derived':
            continue
        kept[key] = entry
    scratchpad['active_filters'] = kept


def copy_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(filters, dict):
        return {}
    copied: dict[str, Any] = {}
    for key, value in filters.items():
        if isinstance(value, dict):
            copied[str(key)] = {
                str(inner_key): _serialize_scalar(inner_value)
                for inner_key, inner_value in value.items()
            }
        elif isinstance(value, list):
            copied[str(key)] = [_serialize_scalar(item) for item in value]
        else:
            copied[str(key)] = _serialize_scalar(value)
    return copied


def remember_data_check(
    scratchpad: dict[str, Any],
    payload: dict[str, Any],
    *,
    provenance: str | None = None,
    source_tool: str | None = None,
    source_turn_id: str | None = None,
) -> None:
    scratchpad['last_data_check'] = {
        'table': payload.get('table'),
        'filters': copy_filters(payload.get('filters')),
        'row_count': int(payload.get('row_count', 0) or 0),
        'min_created_at': payload.get('min_created_at'),
        'max_created_at': payload.get('max_created_at'),
    }
    remember_active_filters(
        scratchpad,
        payload.get('filters'),
        provenance=provenance,
        source_tool=source_tool,
        source_turn_id=source_turn_id,
    )


def remember_catalog_inspection(
    scratchpad: dict[str, Any],
    *,
    table: str,
    columns: list[dict[str, Any]],
) -> None:
    discovered = scratchpad.setdefault('discovered_schema', default_scratchpad()['discovered_schema'])
    if not isinstance(discovered, dict):
        discovered = default_scratchpad()['discovered_schema']
    tables = discovered.setdefault('tables_inspected', [])
    if table not in tables:
        tables.append(table)
    columns_by_table = discovered.setdefault('columns_by_table', {})
    columns_by_table[table] = columns[:50]
    discovered['tables_inspected'] = tables[-10:]
    discovered['columns_by_table'] = columns_by_table
    scratchpad['discovered_schema'] = discovered


def remember_catalog_relations(
    scratchpad: dict[str, Any],
    relations: list[dict[str, Any]],
) -> None:
    discovered = scratchpad.setdefault('discovered_schema', default_scratchpad()['discovered_schema'])
    if not isinstance(discovered, dict):
        discovered = default_scratchpad()['discovered_schema']
    existing = discovered.setdefault('relations_found', [])
    if not isinstance(existing, list):
        existing = []
    existing.extend(relation for relation in relations if isinstance(relation, dict))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for relation in existing:
        key = (
            str(relation.get('constraint_name') or ''),
            str(relation.get('join_expression') or ''),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(relation)
    discovered['relations_found'] = deduped[-20:]
    scratchpad['discovered_schema'] = discovered


def remember_json_structure(
    scratchpad: dict[str, Any],
    *,
    table: str,
    column: str,
    json_structure: dict[str, Any],
) -> None:
    discovered = scratchpad.setdefault('discovered_schema', default_scratchpad()['discovered_schema'])
    if not isinstance(discovered, dict):
        discovered = default_scratchpad()['discovered_schema']
    json_structures = discovered.setdefault('json_structures', {})
    json_structures[f'{table}.{column}'] = json_structure
    discovered['json_structures'] = json_structures
    scratchpad['discovered_schema'] = discovered


def get_latest_resolved_entity_value(
    scratchpad: dict[str, Any] | None,
    entity_type: str,
) -> str | None:
    if not isinstance(scratchpad, dict):
        return None
    resolved_entities = scratchpad.get('resolved_entities', {})
    if not isinstance(resolved_entities, dict):
        return None
    entity_payload = resolved_entities.get(entity_type)
    if not isinstance(entity_payload, dict):
        return None
    matches = entity_payload.get('matches', [])
    if not isinstance(matches, list) or not matches:
        return None
    first_match = matches[0]
    if not isinstance(first_match, dict):
        return None
    value = first_match.get('value')
    return str(value) if value not in (None, '') else None


def _looks_like_run_snapshot(snapshot: dict[str, Any]) -> bool:
    columns = {str(column) for column in snapshot.get('columns', []) if column}
    focus = snapshot.get('focus') or {}
    run_keys = {'run_id', 'run_name', 'eval_type', 'run_date', 'date'}
    return bool(run_keys & columns) or any(key in focus for key in run_keys)


def select_analysis_snapshot(question: str, scratchpad: dict[str, Any] | None) -> dict[str, Any] | None:
    del question
    if not isinstance(scratchpad, dict):
        return None

    history = scratchpad.get('analysis_history', [])
    if not isinstance(history, list):
        history = []
    snapshots = [snapshot for snapshot in history if isinstance(snapshot, dict)]
    last_analysis = scratchpad.get('last_analysis')
    if isinstance(last_analysis, dict):
        snapshots.append(last_analysis)
    if not snapshots:
        return None
    return snapshots[-1]


def should_apply_analysis_context(question: str, last_analysis: dict[str, Any] | None) -> bool:
    del question
    return isinstance(last_analysis, dict)


def build_previous_turn_context(scratchpad: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(scratchpad, dict):
        return None

    last_analysis = scratchpad.get('last_analysis')
    last_evidence = scratchpad.get('last_evidence')
    last_data_check = scratchpad.get('last_data_check')
    outcomes = scratchpad.get('outcomes', [])
    resolved_entities = scratchpad.get('resolved_entities', {})
    # M2: active_filters is now a provenance-wrapped dict; unwrap for
    # prompt context so the model sees the plain key→value map it
    # already understood, while carry-forward policy still runs over
    # the wrapped shape.
    active_filters = active_filter_values(scratchpad)

    has_context = any(
        isinstance(value, dict) and value
        for value in (last_analysis, last_evidence, last_data_check)
    ) or bool(outcomes)
    if not has_context:
        return None

    previous_turn: dict[str, Any] = {}

    recent_tools = [
        str(entry.get('tool'))
        for entry in (outcomes if isinstance(outcomes, list) else [])
        if isinstance(entry, dict) and entry.get('tool')
    ]
    if recent_tools:
        previous_turn['recent_tools'] = recent_tools[-3:]

    latest_outcome = next(
        (
            entry for entry in reversed(outcomes if isinstance(outcomes, list) else [])
            if isinstance(entry, dict)
        ),
        None,
    )
    if isinstance(latest_outcome, dict):
        reason_code = latest_outcome.get('reason_code')
        previous_turn['result_status'] = str(reason_code) if reason_code else 'ok'
        artifact_type = latest_outcome.get('artifact_type')
        if artifact_type:
            previous_turn['artifact_type'] = str(artifact_type)

    if isinstance(last_analysis, dict) and last_analysis:
        question = str(last_analysis.get('question', '')).strip()
        if question:
            previous_turn['user_goal'] = question
        chart_summary = last_analysis.get('chart_summary')
        previous_turn['result_kind'] = (
            str(chart_summary.get('kind'))
            if isinstance(chart_summary, dict) and chart_summary.get('kind')
            else 'analysis'
        )
        pack_context: dict[str, Any] = {}
        row_count = last_analysis.get('row_count')
        if row_count is not None:
            pack_context['row_count'] = row_count
        columns = [str(column) for column in last_analysis.get('columns', []) if column]
        if columns:
            pack_context['columns'] = columns[:_MAX_ANALYSIS_COLUMNS]
        if isinstance(chart_summary, dict) and chart_summary:
            pack_context['chart_summary'] = {
                key: value
                for key, value in chart_summary.items()
                if key in {'kind', 'mark', 'reason_code'}
            }
        scope_recheck_hint = str(last_analysis.get('scope_recheck_hint') or '').strip()
        if scope_recheck_hint:
            pack_context['scope_recheck_hint'] = scope_recheck_hint
        if pack_context:
            previous_turn['pack_context'] = pack_context
    elif isinstance(last_evidence, dict) and last_evidence:
        previous_turn['result_kind'] = 'evidence'
        surface_key = str(last_evidence.get('surface_key') or '').strip()
        if surface_key:
            previous_turn['user_goal'] = f'evidence lookup on {surface_key}'
            previous_turn['pack_context'] = {
                'surface_key': surface_key,
                'record_count': last_evidence.get('record_count'),
            }
    elif isinstance(last_data_check, dict) and last_data_check:
        previous_turn['result_kind'] = 'data_check'
        table = str(last_data_check.get('table') or '').strip()
        if table:
            previous_turn['user_goal'] = f'data check on {table}'
            previous_turn['pack_context'] = {
                'table': table,
                'row_count': last_data_check.get('row_count'),
            }

    if isinstance(active_filters, dict) and active_filters:
        previous_turn['active_filters'] = active_filters

    if isinstance(resolved_entities, dict) and resolved_entities:
        compact_entities: dict[str, list[str]] = {}
        for entity_type, payload in resolved_entities.items():
            if not isinstance(payload, dict):
                continue
            matches = payload.get('matches', [])
            if not isinstance(matches, list) or not matches:
                continue
            values = [
                str(item.get('value'))
                for item in matches[:3]
                if isinstance(item, dict) and item.get('value') not in (None, '')
            ]
            if values:
                compact_entities[str(entity_type)] = values
        if compact_entities:
            previous_turn['active_entities'] = compact_entities

    return previous_turn or None


def build_followup_analysis_context(last_analysis: dict[str, Any] | None) -> str | None:
    if not last_analysis:
        return None

    lines = ['Prior analysis context:']
    question = str(last_analysis.get('question', '')).strip()
    if question:
        lines.append(f'- Previous question: {question}')

    columns = [str(column) for column in last_analysis.get('columns', []) if column]
    if columns:
        lines.append(f"- Result columns: {', '.join(columns[:_MAX_ANALYSIS_COLUMNS])}")

    focus = last_analysis.get('focus') or {}
    if isinstance(focus, dict) and focus:
        lines.append(f'- Top row values: {json.dumps(focus, ensure_ascii=True, sort_keys=True)}')

    preview_rows = last_analysis.get('preview_rows') or []
    if isinstance(preview_rows, list) and preview_rows:
        lines.append(
            f'- Result preview: {json.dumps(preview_rows[:_MAX_ANALYSIS_PREVIEW_ROWS], ensure_ascii=True, sort_keys=True)}'
        )

    scope_recheck_hint = str(last_analysis.get('scope_recheck_hint') or '').strip()
    if scope_recheck_hint:
        lines.append(f'- Scope recheck: {scope_recheck_hint}')

    lines.append('- Reuse exact values from this context when the new question refers to the same run, result, or breakdown.')
    return '\n'.join(lines)


def build_data_query_context(
    question: str,
    scratchpad: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(scratchpad, dict):
        return {}

    context: dict[str, Any] = {}
    discovered_schema = scratchpad.get('discovered_schema')
    if isinstance(discovered_schema, dict) and any(discovered_schema.values()):
        context['discovered_schema'] = discovered_schema

    previous_turn = build_previous_turn_context(scratchpad)
    if previous_turn:
        context['previous_turn'] = previous_turn

    confirmed_constraints = confirmed_constraint_values(scratchpad)
    if confirmed_constraints:
        context['confirmed_constraints'] = confirmed_constraints

    grounded_refs = grounded_ref_values(scratchpad)
    if grounded_refs:
        context['grounded_refs'] = grounded_refs

    last_analysis = select_analysis_snapshot(question, scratchpad)
    if should_apply_analysis_context(question, last_analysis):
        if isinstance(last_analysis, dict):
            context['prior_analysis'] = {
                'question': last_analysis.get('question'),
                'columns': last_analysis.get('columns', []),
                'preview_rows': last_analysis.get('preview_rows', []),
                'sql_used': last_analysis.get('sql_used'),
            }
        active_filters = active_filter_values(scratchpad)
        if active_filters:
            context['active_filters'] = active_filters
        resolved_entities = scratchpad.get('resolved_entities')
        if isinstance(resolved_entities, dict) and resolved_entities:
            context['resolved_entities'] = resolved_entities

    return context


def build_resolved_entity_context(scratchpad: dict[str, Any] | None) -> str | None:
    if not isinstance(scratchpad, dict):
        return None

    resolved_entities = scratchpad.get('resolved_entities', {})
    last_evidence = scratchpad.get('last_evidence')
    if not isinstance(resolved_entities, dict) and not isinstance(last_evidence, dict):
        return None

    lines = ['Resolved entity context:']
    if isinstance(resolved_entities, dict):
        for entity_type, payload in list(resolved_entities.items())[-5:]:
            if not isinstance(payload, dict):
                continue
            matches = payload.get('matches', [])
            if not isinstance(matches, list) or not matches:
                continue
            values = [
                str(match.get('value'))
                for match in matches[:3]
                if isinstance(match, dict) and match.get('value') not in (None, '')
            ]
            if values:
                lines.append(f"- {entity_type}: {', '.join(values)}")

    if isinstance(last_evidence, dict) and last_evidence:
        surface_key = last_evidence.get('surface_key')
        record_count = last_evidence.get('record_count')
        entity_type = last_evidence.get('entity_type')
        entity_value = last_evidence.get('entity_value')
        lines.append(
            f'- Latest evidence: {surface_key} ({record_count} records'
            + (f' for {entity_type}={entity_value}' if entity_type and entity_value else '')
            + ')'
        )

    return '\n'.join(lines) if len(lines) > 1 else None


# ---------------------------------------------------------------------------
# Phase 1 — generic recovery / state_delta merge and render helpers
#
# These are intentionally pack-agnostic: ``apply_state_delta`` accepts the
# typed ``ToolStateDelta`` shape (dict form) and merges each sub-field
# deterministically into the scratchpad without overwriting unrelated
# state. ``build_recovery_context`` renders the compact prior-failure /
# open-threads summary the outer agent needs to decide between retry,
# clarification, and concession. Existing analytics-shaped helpers
# (``active_filters`` / ``resolved_entities``) stay as compatibility
# views and are not replaced.
# ---------------------------------------------------------------------------


_MAX_CONFIRMED_CONSTRAINTS = 20
_MAX_GROUNDED_REFS = 20
_MAX_OPEN_THREADS = 8


def _constraint_dedup_key(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get('key') or ''),
        str(entry.get('source_tool') or ''),
        str(entry.get('provenance') or ''),
    )


def _grounded_ref_dedup_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(entry.get('kind') or ''),
        str(entry.get('key') or ''),
        str(entry.get('source_tool') or ''),
        str(entry.get('provenance') or ''),
    )


def _open_thread_dedup_key(entry: dict[str, Any]) -> tuple[str, str]:
    return (str(entry.get('kind') or ''), str(entry.get('key') or ''))


def _merge_typed_list(
    existing: Any,
    incoming: list[dict[str, Any]],
    *,
    dedup_key,
    max_entries: int,
) -> list[dict[str, Any]]:
    """Append-with-replace merge: same-key incoming entries replace the old.

    Keeps the merge deterministic (last-write-wins per dedup key) while
    avoiding unbounded growth of the scratchpad across turns.
    """
    merged: list[dict[str, Any]] = []
    by_key: dict[Any, int] = {}

    if isinstance(existing, list):
        for entry in existing:
            if not isinstance(entry, dict):
                continue
            key = dedup_key(entry)
            if key in by_key:
                merged[by_key[key]] = entry
            else:
                by_key[key] = len(merged)
                merged.append(entry)

    for entry in incoming:
        if not isinstance(entry, dict):
            continue
        key = dedup_key(entry)
        if key in by_key:
            merged[by_key[key]] = entry
        else:
            by_key[key] = len(merged)
            merged.append(entry)

    if len(merged) > max_entries:
        merged = merged[-max_entries:]
    return merged


def apply_state_delta(
    scratchpad: dict[str, Any],
    state_delta: dict[str, Any] | None,
) -> None:
    """Merge a typed ``state_delta`` patch into the scratchpad.

    Rules (plan Phase 1 §58-73, §386):
    - each sub-field is optional; missing fields leave existing state untouched
    - lists merge with deterministic dedup (same-key incoming replaces old)
    - ``last_result`` / ``failure_record`` overwrite wholesale (they are the
      most recent summary by construction)
    - arbitrary extra keys at the top of the delta are ignored so a pack
      cannot sneak internal state through this slot
    - failure records mirror into ``last_failure`` for recovery-context rendering
    """
    if not isinstance(scratchpad, dict) or not isinstance(state_delta, dict):
        return

    confirmed = state_delta.get('confirmed_constraints')
    if isinstance(confirmed, list) and confirmed:
        scratchpad['confirmed_constraints'] = _merge_typed_list(
            scratchpad.get('confirmed_constraints'),
            [entry for entry in confirmed if isinstance(entry, dict)],
            dedup_key=_constraint_dedup_key,
            max_entries=_MAX_CONFIRMED_CONSTRAINTS,
        )

    grounded = state_delta.get('grounded_refs')
    if isinstance(grounded, list) and grounded:
        scratchpad['grounded_refs'] = _merge_typed_list(
            scratchpad.get('grounded_refs'),
            [entry for entry in grounded if isinstance(entry, dict)],
            dedup_key=_grounded_ref_dedup_key,
            max_entries=_MAX_GROUNDED_REFS,
        )

    threads = state_delta.get('open_threads')
    if isinstance(threads, list) and threads:
        scratchpad['open_threads'] = _merge_typed_list(
            scratchpad.get('open_threads'),
            [entry for entry in threads if isinstance(entry, dict)],
            dedup_key=_open_thread_dedup_key,
            max_entries=_MAX_OPEN_THREADS,
        )

    last_result = state_delta.get('last_result')
    if isinstance(last_result, dict):
        scratchpad['last_result'] = dict(last_result)

    failure = state_delta.get('failure_record')
    if isinstance(failure, dict):
        scratchpad['last_failure'] = dict(failure)


def apply_tool_recovery(
    scratchpad: dict[str, Any],
    recovery: dict[str, Any] | None,
    *,
    reason_code: str | None = None,
    summary: str | None = None,
) -> None:
    """Persist a generic ``recovery`` observation as a compact failure record.

    Called by the harness for every envelope that carries a non-``'none'``
    ``failure_kind``. When a pack already emits ``state_delta.failure_record``
    that write is authoritative and this helper is a no-op (the merged
    record stays in place).
    """
    if not isinstance(scratchpad, dict) or not isinstance(recovery, dict):
        return
    failure_kind = str(recovery.get('failure_kind') or 'none')
    if failure_kind == 'none':
        return
    if isinstance(scratchpad.get('last_failure'), dict):
        # A pack-emitted failure_record is more precise than the generic
        # classification; prefer it.
        existing = scratchpad['last_failure']
        if existing.get('failure_kind') == failure_kind and (
            existing.get('reason_code') or not reason_code
        ):
            return
    scratchpad['last_failure'] = {
        'reason_code': reason_code,
        'failure_kind': failure_kind,
        'recoverable': bool(recovery.get('recoverable')),
        'summary': summary,
    }


def resolve_open_thread(
    scratchpad: dict[str, Any],
    *,
    kind: str,
    key: str,
) -> None:
    """Drop an open thread once it has been answered.

    Called by ``apply_state_delta`` callers (or the harness) after the
    user has resolved the ambiguity. Kept as a public helper so packs
    can close their own threads without reaching into the scratchpad.
    """
    if not isinstance(scratchpad, dict):
        return
    threads = scratchpad.get('open_threads')
    if not isinstance(threads, list):
        return
    scratchpad['open_threads'] = [
        entry
        for entry in threads
        if not (
            isinstance(entry, dict)
            and str(entry.get('kind') or '') == kind
            and str(entry.get('key') or '') == key
        )
    ]


def build_recovery_context(scratchpad: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compact prior-failure + open-threads context for the next prompt.

    Returns ``None`` when there is nothing to surface so the caller can
    omit the block entirely. Kept small and typed on purpose — this
    feeds recovery wording in the outer prompt, not a full replay of
    pack state.
    """
    if not isinstance(scratchpad, dict):
        return None

    raw_failure = scratchpad.get('last_failure')
    raw_threads = scratchpad.get('open_threads')
    raw_last_result = scratchpad.get('last_result')

    last_failure: dict[str, Any] | None = (
        raw_failure if isinstance(raw_failure, dict) else None
    )
    open_threads: list[Any] = raw_threads if isinstance(raw_threads, list) else []
    last_result: dict[str, Any] | None = (
        raw_last_result if isinstance(raw_last_result, dict) else None
    )

    has_failure = bool(
        last_failure
        and last_failure.get('failure_kind') not in (None, 'none')
    )
    has_threads = any(isinstance(entry, dict) for entry in open_threads)
    has_last_result = bool(last_result)

    if not (has_failure or has_threads or has_last_result):
        return None

    context: dict[str, Any] = {}

    if has_failure and last_failure is not None:
        context['prior_failure'] = {
            'failure_kind': str(last_failure.get('failure_kind') or ''),
            'recoverable': bool(last_failure.get('recoverable')),
            'reason_code': last_failure.get('reason_code'),
            'summary': last_failure.get('summary'),
        }

    if has_threads:
        rendered_threads: list[dict[str, Any]] = []
        for entry in open_threads[:_MAX_OPEN_THREADS]:
            if not isinstance(entry, dict):
                continue
            rendered_threads.append({
                'kind': str(entry.get('kind') or ''),
                'key': str(entry.get('key') or ''),
                'message': str(entry.get('message') or ''),
            })
        if rendered_threads:
            context['open_threads'] = rendered_threads

    if has_last_result and last_result is not None:
        context['last_result'] = {
            key: last_result[key]
            for key in ('kind', 'artifact_type', 'row_count', 'reason_code')
            if key in last_result
        }

    return context or None


def render_recovery_context_block(scratchpad: dict[str, Any] | None) -> str | None:
    """Render ``build_recovery_context`` as plain text for the prompt.

    Returns ``None`` when there is nothing to surface. Kept separate from
    the dict form so tests can assert on both shapes and callers can
    pick whichever fits their prompt layout.
    """
    context = build_recovery_context(scratchpad)
    if not context:
        return None

    lines = ['RECOVERY CONTEXT:']
    prior = context.get('prior_failure')
    if isinstance(prior, dict):
        kind = prior.get('failure_kind') or 'unknown'
        recoverable = 'recoverable' if prior.get('recoverable') else 'not recoverable'
        reason = prior.get('reason_code')
        summary = prior.get('summary')
        header = f'- Prior failure: {kind} ({recoverable})'
        if reason:
            header += f' reason_code={reason}'
        lines.append(header)
        if summary:
            lines.append(f'  Summary: {summary}')

    threads = context.get('open_threads')
    if isinstance(threads, list) and threads:
        lines.append('- Open clarification threads:')
        for thread in threads:
            if not isinstance(thread, dict):
                continue
            kind = thread.get('kind') or 'thread'
            key = thread.get('key') or ''
            message = thread.get('message') or ''
            key_suffix = f' [{key}]' if key else ''
            message_suffix = f': {message}' if message else ''
            lines.append(f'  - {kind}{key_suffix}{message_suffix}')

    last_result = context.get('last_result')
    if isinstance(last_result, dict) and last_result:
        parts = []
        for label, key in (('kind', 'kind'), ('artifact', 'artifact_type'), ('rows', 'row_count'), ('reason', 'reason_code')):
            if last_result.get(key) not in (None, ''):
                parts.append(f'{label}={last_result[key]}')
        if parts:
            lines.append('- Last result: ' + ', '.join(parts))

    return '\n'.join(lines) if len(lines) > 1 else None


def confirmed_constraint_values(
    scratchpad: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return ``{key: value}`` for confirmed constraints (compat view).

    Unlike ``active_filter_values`` this reads the Phase-1 typed list, so
    packs that have migrated to ``state_delta`` can expose their durable
    truths alongside the legacy analytics ``active_filters`` surface.
    """
    if not isinstance(scratchpad, dict):
        return {}
    entries = scratchpad.get('confirmed_constraints')
    if not isinstance(entries, list):
        return {}
    out: dict[str, Any] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get('key')
        if key is None:
            continue
        out[str(key)] = entry.get('value')
    return out


def grounded_ref_values(
    scratchpad: dict[str, Any] | None,
) -> dict[str, list[Any]]:
    """Return ``{kind: [values]}`` for grounded refs (compat view)."""
    if not isinstance(scratchpad, dict):
        return {}
    entries = scratchpad.get('grounded_refs')
    if not isinstance(entries, list):
        return {}
    out: dict[str, list[Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get('kind') or '')
        if not kind:
            continue
        out.setdefault(kind, []).append(entry.get('value'))
    return out


def grounded_literal_set(
    scratchpad: dict[str, Any] | None,
    current_filters: dict[str, Any] | None = None,
) -> set[str]:
    """Return the flat set of lower-cased literal values that count as grounding.

    Pack-agnostic: walks Phase-1 typed state (``confirmed_constraints`` /
    ``grounded_refs`` / ``resolved_entities`` / ``active_filters`` /
    ``lookups``) plus any current-turn filter-argument map and flattens
    every scalar value into a single lowercase string set. Integers /
    UUIDs / booleans are all included by string-equality after casting
    — the caller only needs membership.

    Any pack that needs to enforce "only filter on grounded values"
    (analytics SQL validator, future vector-collection-auth, future
    graph-edge-auth) consumes this view via the same lookup surface,
    so there's no pack-to-pack coupling on the scratchpad contents.
    """
    out: set[str] = set()

    def _add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, (list, tuple, set)):
            for v in value:
                _add(v)
            return
        if isinstance(value, dict):
            if 'value' in value:
                _add(value['value'])
            for key in ('min', 'max', 'start', 'end'):
                if key in value:
                    _add(value[key])
            return
        text = str(value).strip()
        if text:
            out.add(text.lower())

    if isinstance(scratchpad, dict):
        for entry in (scratchpad.get('confirmed_constraints') or []):
            if isinstance(entry, dict):
                _add(entry.get('value'))
        for entry in (scratchpad.get('grounded_refs') or []):
            if isinstance(entry, dict):
                _add(entry.get('value'))
        resolved = scratchpad.get('resolved_entities') or {}
        if isinstance(resolved, dict):
            for payload in resolved.values():
                if not isinstance(payload, dict):
                    continue
                for match in (payload.get('matches') or []):
                    if isinstance(match, dict):
                        _add(match.get('value'))
        active = scratchpad.get('active_filters') or {}
        if isinstance(active, dict):
            for entry in active.values():
                if isinstance(entry, dict) and 'value' in entry:
                    _add(entry.get('value'))
                else:
                    _add(entry)
        lookups = scratchpad.get('lookups') or {}
        if isinstance(lookups, dict):
            for payload in lookups.values():
                if not isinstance(payload, dict):
                    continue
                for item in (payload.get('values') or []):
                    if isinstance(item, dict):
                        _add(item.get('value'))

    if isinstance(current_filters, dict):
        for value in current_filters.values():
            _add(value)

    return out
