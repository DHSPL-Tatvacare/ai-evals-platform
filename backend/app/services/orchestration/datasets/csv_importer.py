"""CSV → ImportedDataset parser. Shape validation lives in dataset_validator."""
from __future__ import annotations

import csv
import io
from typing import Optional

from app.services.orchestration.datasets.dataset_validator import (
    DatasetImportError,
    ImportedDataset,
    assemble,
    normalize_columns,
    resolve_max_rows,
    validate_headers,
    validate_id_strategy,
)


def parse_csv(
    raw: bytes,
    *,
    id_strategy: str,
    id_column: Optional[str],
    max_rows: int | None = None,
) -> ImportedDataset:
    validate_id_strategy(id_strategy, id_column)
    cap = resolve_max_rows(max_rows)

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetImportError("CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise DatasetImportError("file has no header row")
    raw_fieldnames = list(reader.fieldnames)
    columns = normalize_columns(raw_fieldnames)
    validate_headers(columns, id_strategy=id_strategy, id_column=id_column)

    rows: list[dict] = []
    for raw_row in reader:
        if len(rows) >= cap:
            raise DatasetImportError(
                f"row cap exceeded: dataset versions are capped at {cap} rows"
            )
        rows.append({
            columns[i]: (raw_row.get(raw_fieldnames[i]) or "").strip()
            for i in range(len(columns))
        })

    return assemble(
        columns, rows, id_strategy=id_strategy, id_column=id_column, max_rows=cap,
    )
