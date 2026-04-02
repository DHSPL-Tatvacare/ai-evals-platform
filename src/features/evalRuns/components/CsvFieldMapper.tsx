import { CsvFieldMapper as SharedCsvFieldMapper } from '@/features/csvImport/components/CsvFieldMapper';

import { CSV_FIELD_SCHEMA, type ColumnMapping } from '../utils/csvSchema';

interface CsvFieldMapperProps {
  /** All column headers found in the uploaded CSV */
  csvHeaders: string[];
  /** Current mapping: target schema field → source CSV column */
  mapping: ColumnMapping;
  /** Called when user changes a mapping */
  onMappingChange: (mapping: ColumnMapping) => void;
  /** Required fields that are missing from the CSV headers */
  missingFields: string[];
}

export function CsvFieldMapper({ csvHeaders, mapping, onMappingChange, missingFields }: CsvFieldMapperProps) {
  return (
    <SharedCsvFieldMapper
      csvHeaders={csvHeaders}
      schema={CSV_FIELD_SCHEMA}
      mapping={mapping}
      onMappingChange={onMappingChange}
      missingFields={missingFields}
    />
  );
}
