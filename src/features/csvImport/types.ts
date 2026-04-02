export interface CsvFieldDef<TGroup extends string = string> {
  name: string;
  description: string;
  required: boolean;
  example: string;
  group: TGroup;
  label?: string;
}

export interface CsvPreviewResult {
  headers: string[];
  rows: string[][];
  totalRowCount: number;
}

export interface HeaderValidation {
  matched: string[];
  missing: string[];
  extra: string[];
  isValid: boolean;
}

export type ColumnMapping = Map<string, string>;
