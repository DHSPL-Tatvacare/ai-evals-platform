import { CsvFieldCallout as SharedCsvFieldCallout } from '@/features/csvImport/components/CsvFieldCallout';

import { CSV_FIELD_SCHEMA, type CsvFieldDef } from '../utils/csvSchema';

const GROUP_LABELS: Record<CsvFieldDef['group'], string> = {
  content: 'Content',
  identity: 'Identity',
  metadata: 'Metadata',
};

const GROUP_ORDER: CsvFieldDef['group'][] = ['content', 'identity', 'metadata'];

export function CsvFieldCallout() {
  return (
    <SharedCsvFieldCallout
      schema={CSV_FIELD_SCHEMA}
      groupLabels={GROUP_LABELS}
      groupOrder={GROUP_ORDER}
    />
  );
}
