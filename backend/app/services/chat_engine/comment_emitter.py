"""Emit ``COMMENT ON COLUMN`` statements from the per-app manifest.

Applied to the live database by ``backend/scripts/sync_column_comments.py``,
invoked from the FastAPI lifespan (the Sherlock SQL agent runs in the
backend process and reads ``pg_description``; the worker never calls this).
Keeps the ``pg_description`` rows the SQL agent reads consistent with the
YAML manifest.
"""
from __future__ import annotations

from app.services.chat_engine.manifest import AppManifest, get_manifest, load_all_manifests


def _render_comment_body(col) -> str:
    parts: list[str] = []
    if col.description:
        parts.append(col.description.rstrip("."))
    parts.append(f"Role: {col.role}.")
    if col.data_type:
        parts.append(f"DataType: {col.data_type}.")
    if col.semantic_type:
        parts.append(f"SemanticType: {col.semantic_type}.")
    if col.allowed_values:
        parts.append("Values: " + ", ".join(str(v) for v in col.allowed_values) + ".")
    if col.ordering:
        parts.append("Ordering: " + ", ".join(str(v) for v in col.ordering) + ".")
    if col.synonyms:
        parts.append("Synonyms: " + ", ".join(col.synonyms) + ".")
    if col.unit:
        parts.append(f"Unit: {col.unit}.")
    if col.measure_kind:
        parts.append(f"MeasureKind: {col.measure_kind}.")
    if col.chartable is not None:
        parts.append(f"Chartable: {'true' if col.chartable else 'false'}.")
    body = " ".join(parts)
    body = body.replace("..", ".")
    return body


def emit_column_comments(*, app_id: str | None = None) -> list[str]:
    """Return a list of ``COMMENT ON COLUMN …`` SQL statements.

    If ``app_id`` is given, only that app's manifest contributes. Otherwise
    all registered manifests contribute, de-duplicated by ``(schema, table,
    column)``.

    Statements are schema-qualified using each table's ``effective_schema``
    (``public`` for Phase 1; ``platform``/``analytics`` once revision 0006+
    moves tables). Roadmap 01 §9.6 — application code MUST schema-qualify
    every reference.
    """
    manifests: list[AppManifest]
    manifests = [get_manifest(app_id)] if app_id else list(load_all_manifests().values())

    stmts: list[str] = []
    emitted: set[tuple[str, str, str]] = set()
    for manifest in manifests:
        for table_name, table in manifest.catalog_tables.items():
            schema_name = table.effective_schema
            for col_name, col in table.columns.items():
                key = (schema_name, table_name, col_name)
                if key in emitted:
                    continue
                body = _render_comment_body(col).replace("'", "''")
                stmts.append(
                    f"COMMENT ON COLUMN {schema_name}.{table_name}.{col_name} IS '{body}'"
                )
                emitted.add(key)
    return stmts
