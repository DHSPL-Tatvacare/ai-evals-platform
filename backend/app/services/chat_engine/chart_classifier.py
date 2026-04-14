"""Data-shape-driven chart type classification.

The classifier inspects analyze result columns to determine which
Recharts chart types are eligible for the data. No app-specific logic —
only data shape and optional semantic model dimension metadata.
"""
from __future__ import annotations

import re
from typing import Any

# Patterns for detecting temporal columns
_TEMPORAL_NAME_PATTERN = re.compile(
    r'(date|time|month|week|year|quarter|day|period|created|updated)',
    re.IGNORECASE,
)
_ISO_DATE_PATTERN = re.compile(
    r'^\d{4}[-/]\d{2}([-/]\d{2})?([T ]\d{2}:\d{2}(:\d{2})?)?',
)


def _is_numeric_value(value: Any) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    return False


def _is_temporal_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_ISO_DATE_PATTERN.match(value.strip()))


def classify_columns(
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    dimensions: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Classify each column as numeric, temporal, ordered_categorical, or categorical.

    Args:
        columns: ordered column names from the analyze result.
        rows: data rows (list of dicts).
        dimensions: optional semantic model dimension metadata. Each dict
            may include an ``ordering`` key (list of ordered values) that
            promotes the column to ``ordered_categorical``.

    Returns:
        dict mapping column name to type string.
    """
    ordered_dims: set[str] = set()
    if dimensions:
        for dim in dimensions:
            if isinstance(dim, dict) and dim.get('ordering'):
                ordered_dims.add(str(dim.get('name', '')))

    result: dict[str, str] = {}
    for col in columns:
        # Check ordered categorical first (from semantic model metadata)
        if col in ordered_dims:
            result[col] = 'ordered_categorical'
            continue

        # Sample non-null values
        values = [
            row[col]
            for row in rows
            if isinstance(row, dict) and col in row and row[col] is not None
        ]

        if not values:
            result[col] = 'categorical'
            continue

        # Check numeric
        if all(_is_numeric_value(v) for v in values):
            result[col] = 'numeric'
            continue

        # Check temporal — by column name or by value pattern
        if _TEMPORAL_NAME_PATTERN.search(col):
            result[col] = 'temporal'
            continue
        if all(_is_temporal_value(v) for v in values):
            result[col] = 'temporal'
            continue

        result[col] = 'categorical'

    return result


# ── Chart type registry ──────────────────────────────────────────────

CHART_TYPE_REGISTRY: dict[str, dict[str, Any]] = {
    'bar':            {'min_categorical': 1, 'min_numeric': 1, 'max_series': 1},
    'horizontal_bar': {'min_categorical': 1, 'min_numeric': 1, 'max_series': 1, 'prefer_when': 'high_cardinality'},
    'stacked_bar':    {'min_categorical': 1, 'min_numeric': 2},
    'grouped_bar':    {'min_categorical': 1, 'min_numeric': 2},
    'line':           {'min_ordinal': 1, 'min_numeric': 1},
    'area':           {'min_ordinal': 1, 'min_numeric': 1},
    'stacked_area':   {'min_ordinal': 1, 'min_numeric': 2},
    'pie':            {'min_categorical': 1, 'min_numeric': 1, 'max_rows': 12},
    'donut':          {'min_categorical': 1, 'min_numeric': 1, 'max_rows': 12},
    'scatter':        {'min_numeric': 2},
    'radar':          {'min_categorical': 1, 'min_numeric': 1, 'min_rows': 3, 'max_rows': 10},
    'funnel':         {'min_categorical': 1, 'min_numeric': 1, 'requires': 'ordered_categorical'},
    'treemap':        {'min_categorical': 1, 'min_numeric': 1, 'min_rows': 3},
    'radial_bar':     {'min_categorical': 1, 'min_numeric': 1, 'max_rows': 8},
    'composed':       {'min_ordinal': 1, 'min_numeric': 2},
}

_HIGH_CARDINALITY_THRESHOLD = 8


def get_eligible_charts(
    column_types: dict[str, str],
    *,
    row_count: int,
) -> list[str]:
    """Return chart types eligible for the given data shape, ordered by fit.

    Ranking:
    1. Charts with ``requires`` constraints that match (specificity wins)
    2. Charts with ``prefer_when`` conditions that match
    3. General-purpose charts
    """
    if not column_types:
        return []

    counts: dict[str, int] = {
        'numeric': 0,
        'categorical': 0,
        'temporal': 0,
        'ordered_categorical': 0,
    }
    for col_type in column_types.values():
        counts[col_type] = counts.get(col_type, 0) + 1

    # Ordinal = temporal + ordered_categorical
    ordinal_count = counts['temporal'] + counts['ordered_categorical']
    # Categorical includes ordered_categorical and temporal (they can group)
    categorical_count = counts['categorical'] + counts['ordered_categorical'] + counts['temporal']

    has_ordered = counts['ordered_categorical'] > 0

    eligible: list[tuple[int, str]] = []  # (priority, type_name)

    for chart_type, reqs in CHART_TYPE_REGISTRY.items():
        # Check min_numeric
        if counts['numeric'] < reqs.get('min_numeric', 0):
            continue
        # Check min_categorical (temporal and ordered satisfy this)
        if categorical_count < reqs.get('min_categorical', 0):
            continue
        # Check min_ordinal (temporal and ordered_categorical satisfy this)
        if ordinal_count < reqs.get('min_ordinal', 0):
            continue
        # Check row count bounds
        if row_count < reqs.get('min_rows', 0):
            continue
        if 'max_rows' in reqs and row_count > reqs['max_rows']:
            continue
        # Check requires constraint
        requires = reqs.get('requires')
        if requires == 'ordered_categorical' and not has_ordered:
            continue

        # Assign priority (lower = better)
        priority = 30  # default: general purpose
        if requires and requires == 'ordered_categorical' and has_ordered:
            priority = 10  # specificity match
        elif reqs.get('prefer_when') == 'high_cardinality' and row_count >= _HIGH_CARDINALITY_THRESHOLD:
            priority = 20  # preference match
        elif reqs.get('prefer_when') == 'high_cardinality' and row_count < _HIGH_CARDINALITY_THRESHOLD:
            priority = 35  # demote when preference doesn't match

        eligible.append((priority, chart_type))

    eligible.sort(key=lambda item: item[0])
    return [chart_type for _, chart_type in eligible]
