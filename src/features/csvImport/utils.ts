import type { ColumnMapping, CsvFieldDef, CsvPreviewResult, HeaderValidation } from './types';

function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (i + 1 < line.length && line[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        current += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      fields.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }

  fields.push(current.trim());
  return fields;
}

export function getRequiredFieldNames(schema: CsvFieldDef[]): string[] {
  return schema.filter((field) => field.required).map((field) => field.name);
}

export function getAllFieldNames(schema: CsvFieldDef[]): string[] {
  return schema.map((field) => field.name);
}

export function parseCsvPreview(text: string, maxRows = 10): CsvPreviewResult {
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length === 0) {
    return { headers: [], rows: [], totalRowCount: 0 };
  }

  const headers = parseCsvLine(lines[0]);
  const dataLines = lines.slice(1);
  const rows = dataLines.slice(0, maxRows).map((line) => {
    const cells = parseCsvLine(line);
    while (cells.length < headers.length) {
      cells.push('');
    }
    return cells.slice(0, headers.length);
  });

  return { headers, rows, totalRowCount: dataLines.length };
}

export function parseCsvRecords(text: string): Record<string, string>[] {
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length === 0) {
    return [];
  }

  const headers = parseCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    const record: Record<string, string> = {};
    headers.forEach((header, index) => {
      record[header] = cells[index]?.trim() ?? '';
    });
    return record;
  });
}

export function validateCsvHeaders(headers: string[], schema: CsvFieldDef[]): HeaderValidation {
  const headerSet = new Set(headers.map((header) => header.trim().toLowerCase()));
  const schemaFieldNames = getAllFieldNames(schema);
  const schemaSet = new Set(schemaFieldNames.map((name) => name.toLowerCase()));

  const matched: string[] = [];
  const missing: string[] = [];

  for (const field of schema) {
    if (headerSet.has(field.name.toLowerCase())) {
      matched.push(field.name);
    } else if (field.required) {
      missing.push(field.name);
    }
  }

  const extra = headers.filter((header) => !schemaSet.has(header.trim().toLowerCase()));

  return {
    matched,
    missing,
    extra,
    isValid: missing.length === 0,
  };
}

export function remapCsvContent(text: string, mapping: ColumnMapping): string {
  const lines = text.split(/\r?\n/);
  if (lines.length === 0) {
    return text;
  }

  const headers = parseCsvLine(lines[0]);
  const reverseMap = new Map<string, string>();
  for (const [target, source] of mapping) {
    reverseMap.set(source.toLowerCase(), target);
  }

  const remappedHeaders = headers.map((header) => reverseMap.get(header.trim().toLowerCase()) ?? header);
  const headerLine = remappedHeaders
    .map((header) => (header.includes(',') || header.includes('"') ? `"${header}"` : header))
    .join(',');

  return [headerLine, ...lines.slice(1)].join('\n');
}
