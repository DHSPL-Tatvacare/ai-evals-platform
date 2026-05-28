export type MappingSourceKind = 'payload' | 'static';

export interface SourceKindMappingRow {
  source_kind: MappingSourceKind;
  payload_field?: string;
  static_value?: string;
}

export function normalizeSourceKindMappingRow<T extends SourceKindMappingRow>(
  row: T,
  nextSourceKind: MappingSourceKind,
): T {
  const nextRow = {
    ...row,
    source_kind: nextSourceKind,
  } as T & { payload_field?: string; static_value?: string };

  if (nextSourceKind === 'payload') {
    nextRow.payload_field = typeof row.payload_field === 'string' ? row.payload_field : '';
    delete nextRow.static_value;
    return nextRow as T;
  }

  nextRow.static_value = typeof row.static_value === 'string' ? row.static_value : '';
  delete nextRow.payload_field;
  return nextRow as T;
}
