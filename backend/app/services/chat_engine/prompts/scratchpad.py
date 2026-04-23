"""Layer 4: session scratchpad rendered each turn."""
from __future__ import annotations

from typing import Any

from app.services.report_builder.scratchpad_state import build_previous_turn_context

_MAX_FINDINGS = 15
_MAX_ERRORS = 5
_MAX_DISCOVERY_DIMENSIONS = 6
_MAX_LOOKUPS = 5
_MAX_ANALYSIS_COLUMNS = 8
_MAX_ANALYSIS_PREVIEW_ROWS = 2
_MAX_FILTERS = 8
_MAX_SCHEMA_TABLES = 4
_MAX_SCHEMA_COLUMNS = 6
# Phase 2: outer agent sees the most recent deterministic tool outcomes
# as a compact per-tool record (reason_code + artifact_type + counts) so
# cross-turn reasoning is driven by typed codes, not re-parsed prose.
_MAX_OUTCOMES = 8


def render(session: dict[str, Any]) -> str:
    pad = session.get('scratchpad')
    if not pad:
        return ''

    findings = pad.get('findings', [])
    errors = pad.get('errors', [])
    discovery = pad.get('discovery')
    lookups = pad.get('lookups', {})
    resolved_entities = pad.get('resolved_entities', {})
    active_filters = pad.get('active_filters', {})
    discovered_schema = pad.get('discovered_schema')
    last_data_check = pad.get('last_data_check')
    last_analysis = pad.get('last_analysis')
    last_evidence = pad.get('last_evidence')
    outcomes = pad.get('outcomes', [])
    previous_turn = build_previous_turn_context(pad)

    has_discovered_schema = False
    if isinstance(discovered_schema, dict):
        has_discovered_schema = any(
            value
            for value in (
                discovered_schema.get('tables_inspected'),
                discovered_schema.get('columns_by_table'),
                discovered_schema.get('relations_found'),
                discovered_schema.get('json_structures'),
            )
        )

    if not findings and not errors and not discovery and not lookups and not resolved_entities and not active_filters and not has_discovered_schema and not last_data_check and not last_analysis and not last_evidence and not outcomes:
        return ''

    lines = ['SESSION STATE:']

    # Phase 2: the outer agent reasons over the structured outcome log
    # (deterministic ``reason_code`` + artifact shape + counts) first,
    # before prose findings. This is the carry-forward contract §Phase-2
    # step 6 calls for: typed codes cross turns, not re-parsed text.
    if isinstance(outcomes, list) and outcomes:
        lines.append('Recent tool outcomes (deterministic):')
        for entry in outcomes[-_MAX_OUTCOMES:]:
            if not isinstance(entry, dict):
                continue
            tool = str(entry.get('tool') or 'tool')
            reason_code = entry.get('reason_code')
            artifact_type = entry.get('artifact_type')
            counts = entry.get('counts') or {}
            parts = []
            if reason_code:
                parts.append(f'reason_code={reason_code}')
            if artifact_type:
                parts.append(f'artifact={artifact_type}')
            rows = counts.get('rows') if isinstance(counts, dict) else None
            records = counts.get('records') if isinstance(counts, dict) else None
            if rows:
                parts.append(f'rows={rows}')
            if records:
                parts.append(f'records={records}')
            tail = f" ({', '.join(parts)})" if parts else ''
            lines.append(f'- {tool}{tail}')

    if isinstance(previous_turn, dict) and previous_turn:
        lines.append('Previous turn context:')
        user_goal = str(previous_turn.get('user_goal') or '').strip()
        if user_goal:
            lines.append(f'- User goal: {user_goal}')
        recent_tools = previous_turn.get('recent_tools')
        if isinstance(recent_tools, list) and recent_tools:
            rendered_tools = ', '.join(str(tool) for tool in recent_tools if tool)
            if rendered_tools:
                lines.append(f'- Recent tools: {rendered_tools}')
        result_kind = str(previous_turn.get('result_kind') or '').strip()
        if result_kind:
            lines.append(f'- Result kind: {result_kind}')
        result_status = str(previous_turn.get('result_status') or '').strip()
        if result_status:
            lines.append(f'- Result status: {result_status}')

    if findings:
        lines.append('Findings so far:')
        for finding in findings[-_MAX_FINDINGS:]:
            lines.append(f'- {finding}')

    # Audit fix: ``composed_report`` used to be rendered here. That was
    # report-builder pack state leaking into the Sherlock-wide scratchpad
    # prompt. Blueprint preview memory now reaches the agent through the
    # prior-turn tool outcome envelope (visible via the Responses API
    # ``previous_response_id``); the generic scratchpad stays pack-agnostic.

    if discovery:
        dimensions = discovery.get('dimensions', [])
        metrics = discovery.get('metrics', [])
        surfaces = discovery.get('surfaces', [])
        time_range = discovery.get('time_range') or {}
        earliest = time_range.get('earliest')
        latest = time_range.get('latest')
        lines.append(
            f'Discovery cache: {len(dimensions)} dimensions, {len(metrics)} metrics'
            + (f', range {earliest} to {latest}' if earliest and latest else '')
        )
        if surfaces:
            lines.append(f"- Evidence surfaces: {', '.join(str(surface.get('key')) for surface in surfaces[:4] if surface.get('key'))}")
        for dimension in dimensions[:_MAX_DISCOVERY_DIMENSIONS]:
            values = [
                str(item.get('value'))
                for item in dimension.get('values', [])[:3]
                if item.get('value') not in (None, '')
            ]
            sample = ', '.join(values) if values else 'no sample values'
            lines.append(f"- {dimension.get('name', 'unknown')}: {sample}")

    if lookups:
        lines.append('Resolved values:')
        for dimension, result in list(lookups.items())[-_MAX_LOOKUPS:]:
            values = [
                str(item.get('value'))
                for item in result.get('values', [])[:3]
                if item.get('value') not in (None, '')
            ]
            sample = ', '.join(values) if values else 'no matches'
            lines.append(f'- {dimension}: {sample}')

    if resolved_entities:
        lines.append('Resolved entities:')
        for entity_type, payload in list(resolved_entities.items())[-_MAX_LOOKUPS:]:
            matches = payload.get('matches', []) if isinstance(payload, dict) else []
            values = [
                str(item.get('value'))
                for item in matches[:3]
                if isinstance(item, dict) and item.get('value') not in (None, '')
            ]
            sample = ', '.join(values) if values else 'no matches'
            lines.append(f'- {entity_type}: {sample}')

    if active_filters:
        lines.append('Active filters to carry forward unless the user changes them:')
        for key, value in list(active_filters.items())[:_MAX_FILTERS]:
            lines.append(f'- {key}: {value}')

    if discovered_schema:
        tables = discovered_schema.get('tables_inspected', []) if isinstance(discovered_schema, dict) else []
        columns_by_table = discovered_schema.get('columns_by_table', {}) if isinstance(discovered_schema, dict) else {}
        relations_found = discovered_schema.get('relations_found', []) if isinstance(discovered_schema, dict) else []
        json_structures = discovered_schema.get('json_structures', {}) if isinstance(discovered_schema, dict) else {}
        if tables or columns_by_table or relations_found or json_structures:
            lines.append('Discovered schema subset:')
        for table in tables[:_MAX_SCHEMA_TABLES]:
            table_columns = columns_by_table.get(table, []) if isinstance(columns_by_table, dict) else []
            rendered_columns = []
            for column in table_columns[:_MAX_SCHEMA_COLUMNS]:
                if not isinstance(column, dict):
                    continue
                name = str(column.get('column_name') or column.get('name') or '')
                role = str(column.get('parsed_comment', {}).get('role') or column.get('role') or '').strip()
                rendered_columns.append(f'{name} ({role})' if role else name)
            if rendered_columns:
                lines.append(f"- {table}: {', '.join(rendered_columns)}")
            else:
                lines.append(f'- {table}')
        if relations_found:
            for relation in relations_found[:4]:
                if not isinstance(relation, dict):
                    continue
                join_expression = relation.get('join_expression')
                if join_expression:
                    lines.append(f'- Join path: {join_expression}')
        if json_structures:
            for key in list(json_structures.keys())[:3]:
                lines.append(f'- JSON structure inspected: {key}')

    if last_data_check:
        lines.append('Latest data check:')
        lines.append(f"- Table: {last_data_check.get('table', 'unknown')}")
        lines.append(f"- Rows: {last_data_check.get('row_count', 0)}")
        if last_data_check.get('filters'):
            lines.append(f"- Filters: {last_data_check.get('filters')}")

    if last_analysis:
        question = str(last_analysis.get('question', '')).strip()
        row_count = last_analysis.get('row_count')
        columns = [
            str(column)
            for column in last_analysis.get('columns', [])[:_MAX_ANALYSIS_COLUMNS]
            if column
        ]
        preview_rows = last_analysis.get('preview_rows', [])[:_MAX_ANALYSIS_PREVIEW_ROWS]
        lines.append('Latest analysis context:')
        if question:
            lines.append(f'- Question: {question}')
        if row_count is not None:
            lines.append(f'- Rows: {row_count}')
        if columns:
            lines.append(f"- Columns: {', '.join(columns)}")
        column_metadata = last_analysis.get('columns_metadata', [])
        if isinstance(column_metadata, list) and column_metadata:
            rendered_roles = []
            for column in column_metadata[:_MAX_ANALYSIS_COLUMNS]:
                if not isinstance(column, dict) or not column.get('name'):
                    continue
                rendered_roles.append(f"{column['name']} ({column.get('role', 'dimension')})")
            if rendered_roles:
                lines.append(f"- Column roles: {', '.join(rendered_roles)}")
        for row in preview_rows:
            if isinstance(row, dict) and row:
                sample = ', '.join(f'{key}={value}' for key, value in row.items())
                lines.append(f'- Row: {sample}')
        warnings = last_analysis.get('warnings', [])
        if warnings:
            warning_codes = [
                str(item.get('code'))
                for item in warnings[:4]
                if isinstance(item, dict) and item.get('code')
            ]
            if warning_codes:
                lines.append(f"- Result warnings: {', '.join(warning_codes)}")
        # Phase 5: kind-discriminated hint from the chart-contract orchestrator.
        # Replaces the old ``chart_options.suggested/eligible_types`` read so
        # the scratchpad describes what the user actually saw (chart, KPI,
        # table-with-reason, etc.) instead of speculative chart-type lists.
        chart_summary = last_analysis.get('chart_summary')
        if isinstance(chart_summary, dict):
            kind = str(chart_summary.get('kind') or '').strip()
            reason = chart_summary.get('reason_code')
            mark = chart_summary.get('mark')
            if kind == 'chart' and mark:
                line = f'- Last result rendered as a {mark} chart.'
                if reason:
                    line += f' (reason: {reason})'
                lines.append(line)
            elif kind == 'kpi':
                lines.append('- Last result rendered as a single-value KPI.')
            elif kind == 'summary':
                lines.append('- Last result rendered as a single-row field summary.')
            elif kind == 'table':
                reason_text = f' (reason: {reason})' if reason else ''
                lines.append(f'- Last result rendered as a table{reason_text}.')
            elif kind == 'empty':
                lines.append('- Last result was empty.')
        scope_recheck_hint = str(last_analysis.get('scope_recheck_hint') or '').strip()
        if scope_recheck_hint:
            lines.append(f'- Scope recheck: {scope_recheck_hint}')

    if last_evidence:
        lines.append('Latest evidence context:')
        lines.append(f"- Surface: {last_evidence.get('surface_key', 'unknown')}")
        if last_evidence.get('record_count') is not None:
            lines.append(f"- Records: {last_evidence.get('record_count')}")
        if last_evidence.get('entity_type') and last_evidence.get('entity_value'):
            lines.append(f"- Filter: {last_evidence.get('entity_type')}={last_evidence.get('entity_value')}")

    if errors:
        lines.append('Recent errors:')
        for error in errors[-_MAX_ERRORS:]:
            lines.append(f'- {error}')

    return '\n'.join(lines)
