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
_RUN_SCOPE_FILTER_KEYS = {'run_name', 'run_reference'}
_EMPTY_REASON_CODES = {'CG_EMPTY'}


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
    app_scope_terms: list[str] | None = None,
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
        'scope_recheck_hint': _build_scope_recheck_hint(result, app_scope_terms=app_scope_terms),
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


def _build_scope_recheck_hint(
    result: dict[str, Any],
    *,
    app_scope_terms: list[str] | None,
) -> str | None:
    normalized_scope_terms = {
        _normalize_scope_text(term)
        for term in (app_scope_terms or [])
        if _normalize_scope_text(term)
    }
    if not normalized_scope_terms:
        return None

    chart_summary = _chart_summary_from_result(result)
    if not isinstance(chart_summary, dict):
        return None
    if str(chart_summary.get('reason_code') or '').strip() not in _EMPTY_REASON_CODES:
        return None

    matched = _matching_run_scope_alias(
        result.get('applied_filters'),
        normalized_scope_terms=normalized_scope_terms,
    )
    if not matched:
        return None

    return (
        f"The last result was empty after filtering run_name/run_reference to '{matched}', "
        'which also matches the current app alias. If the next turn only changes chart shape or presentation, '
        'rerun the analysis without that inferred run-name filter unless the user explicitly asks for a run name.'
    )


def _matching_run_scope_alias(
    filters: Any,
    *,
    normalized_scope_terms: set[str],
) -> str | None:
    if not isinstance(filters, dict):
        return None
    for key, value in filters.items():
        if str(key).strip().lower() not in _RUN_SCOPE_FILTER_KEYS:
            continue
        normalized_value = _normalize_filter_value(value)
        if normalized_value and normalized_value in normalized_scope_terms:
            return normalized_value
    return None


def _normalize_filter_value(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = _normalize_scope_text(value)
        return normalized or None
    if isinstance(value, list):
        for item in value:
            normalized = _normalize_filter_value(item)
            if normalized:
                return normalized
        return None
    if isinstance(value, dict):
        for key in ('value', 'text', 'search', 'contains', 'equals'):
            if key in value:
                normalized = _normalize_filter_value(value.get(key))
                if normalized:
                    return normalized
    return None


def _normalize_scope_text(text: str) -> str:
    return ' '.join(part for part in re.split(r'[^a-z0-9]+', str(text or '').strip().lower()) if part)


def push_analysis_snapshot(scratchpad: dict[str, Any], snapshot: dict[str, Any], *, max_entries: int = 5) -> None:
    history = scratchpad.setdefault('analysis_history', [])
    if not isinstance(history, list):
        history = []
    history.append(snapshot)
    scratchpad['analysis_history'] = history[-max_entries:]
    scratchpad['last_analysis'] = snapshot


def remember_resolved_entities(
    scratchpad: dict[str, Any],
    *,
    entity_type: str,
    search: str,
    matches: list[dict[str, Any]],
) -> None:
    resolved_entities = scratchpad.setdefault('resolved_entities', {})
    if not isinstance(resolved_entities, dict):
        resolved_entities = {}
    resolved_entities[entity_type] = {
        'search': search,
        'matches': matches[:10],
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
) -> None:
    scratchpad['active_filters'] = copy_filters(filters)


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
) -> None:
    scratchpad['last_data_check'] = {
        'table': payload.get('table'),
        'filters': copy_filters(payload.get('filters')),
        'row_count': int(payload.get('row_count', 0) or 0),
        'min_created_at': payload.get('min_created_at'),
        'max_created_at': payload.get('max_created_at'),
    }
    remember_active_filters(scratchpad, payload.get('filters'))


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
    active_filters = scratchpad.get('active_filters', {})

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
        previous_turn['active_filters'] = copy_filters(active_filters)

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

    last_analysis = select_analysis_snapshot(question, scratchpad)
    if should_apply_analysis_context(question, last_analysis):
        if isinstance(last_analysis, dict):
            context['prior_analysis'] = {
                'question': last_analysis.get('question'),
                'columns': last_analysis.get('columns', []),
                'preview_rows': last_analysis.get('preview_rows', []),
                'sql_used': last_analysis.get('sql_used'),
            }
            scope_recheck_hint = str(last_analysis.get('scope_recheck_hint') or '').strip()
            if scope_recheck_hint:
                context['prior_analysis']['scope_recheck_hint'] = scope_recheck_hint
        active_filters = scratchpad.get('active_filters')
        if isinstance(active_filters, dict) and active_filters:
            context['active_filters'] = copy_filters(active_filters)
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
