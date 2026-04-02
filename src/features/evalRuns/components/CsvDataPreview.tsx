import { CsvDataPreview as SharedCsvDataPreview } from '@/features/csvImport/components/CsvDataPreview';

import { CSV_FIELD_SCHEMA, type ColumnMapping, type CsvPreviewResult } from '../utils/csvSchema';

interface CsvDataPreviewProps {
  preview: CsvPreviewResult;
  /** Column mapping applied — shows remapped target names as column tips */
  columnMapping?: ColumnMapping;
}

/**
 * Inline scrollable table preview of the first N rows of uploaded CSV data.
 * Headers that match required schema fields get a subtle highlight.
 */
export function CsvDataPreview({ preview, columnMapping }: CsvDataPreviewProps) {
  return (
    <SharedCsvDataPreview preview={preview} schema={CSV_FIELD_SCHEMA} columnMapping={columnMapping} />
  );
}
