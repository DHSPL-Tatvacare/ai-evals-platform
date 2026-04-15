"""Deterministic verification for Sherlock v2 SQL results."""
from __future__ import annotations

import re
from typing import Any

_DISTRIBUTION_HINT_PATTERN = re.compile(
    r'\b(by|breakdown|distribution|compare|versus|vs\.?|top|most|least|per)\b',
    re.IGNORECASE,
)


def verify_query_result(
    *,
    question: str,
    sql: str,
    rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    row_count = len(rows)
    warnings: list[dict[str, Any]] = []

    if row_count == 0:
        warnings.append({
            'code': 'empty_result',
            'message': 'Query returned no rows. Filters may be too restrictive.',
        })

    if row_count > 100:
        warnings.append({
            'code': 'large_result_set',
            'message': 'Large result set. Consider adding filters.',
            'row_count': row_count,
        })

    if row_count == 1 and _DISTRIBUTION_HINT_PATTERN.search(question or ''):
        warnings.append({
            'code': 'possible_missing_group_by',
            'message': 'Only 1 row returned. The query may be missing a GROUP BY.',
        })

    for column in columns:
        name = str(column.get('name') or '').strip()
        if not name or not rows:
            continue
        if all(row.get(name) is None for row in rows):
            warnings.append({
                'code': 'all_null_column',
                'message': f"Column '{name}' is entirely NULL. Check join conditions or selected fields.",
                'column': name,
            })

    sql_lower = sql.lower()
    for column in columns:
        if not column.get('pre_aggregated'):
            continue
        source_expression = str(
            column.get('source_expression')
            or column.get('source_column')
            or column.get('name')
            or ''
        ).strip()
        if not source_expression:
            continue
        expression_pattern = re.escape(source_expression.lower())
        if re.search(rf'\b(sum|avg)\s*\(\s*{expression_pattern}\s*\)', sql_lower):
            warnings.append({
                'code': 'pre_aggregated_measure',
                'message': f"'{column.get('name')}' is pre-aggregated. Summing or averaging it again may produce misleading results.",
                'column': str(column.get('name') or ''),
            })

    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for warning in warnings:
        key = (str(warning.get('code') or ''), str(warning.get('column') or ''))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped
