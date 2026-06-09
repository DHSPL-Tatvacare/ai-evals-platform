import { useMemo, useState } from 'react';

import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Combobox } from '@/components/ui/Combobox';
import { PredicateBuilder } from '@/features/orchestration/components/editors/PredicateBuilder';
import type { PredicateAst } from '@/features/orchestration/types';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import { useCrmMappingDraftStore } from '@/stores/crmMappingDraftStore';

import { useFieldValues, useFilterCapabilities } from '../queries/crmSourceQueries';

/** Optional row-level filter over the mapped fields. Operators come from the adapter's
 *  filter-capabilities; live distinct values are pulled per selected field. Empty = no filter. */
export function FilterSection({
  connectionId,
  recordType,
  mappedFields,
}: {
  connectionId: string;
  recordType: string;
  mappedFields: string[];
}) {
  const filterPredicate = useCrmMappingDraftStore((s) => s.filterPredicate);
  const setFilterPredicate = useCrmMappingDraftStore((s) => s.setFilterPredicate);

  const capabilities = useFilterCapabilities(connectionId, recordType);

  // Filterable fields the adapter declares, intersected with what the draft maps.
  const fieldOptions = useMemo(() => {
    const mapped = new Set(mappedFields);
    const declared = (capabilities.data?.fields ?? []).map((f) => f.field).filter((f) => mapped.has(f));
    return declared.length > 0 ? declared : mappedFields;
  }, [capabilities.data, mappedFields]);

  if (mappedFields.length === 0) {
    return (
      <Alert variant="info">
        Map at least one field, then add filters here to narrow which records land in this dataset.
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {capabilities.isError ? (
        <Alert variant="warning">
          {summarizeApiErrorBody(decodeApiError(capabilities.error), 'Could not load filterable fields.')}
        </Alert>
      ) : null}
      <PredicateBuilder
        value={filterPredicate}
        onChange={(next: PredicateAst) => setFilterPredicate(next)}
        fieldOptions={fieldOptions}
      />
      <FieldValueBrowser
        connectionId={connectionId}
        recordType={recordType}
        fields={fieldOptions}
      />
    </div>
  );
}

/** Live distinct values for a chosen mapped field — guidance while building a predicate. */
function FieldValueBrowser({
  connectionId,
  recordType,
  fields,
}: {
  connectionId: string;
  recordType: string;
  fields: string[];
}) {
  const [field, setField] = useState<string | null>(null);
  const valuesQuery = useFieldValues(connectionId, recordType, field);
  const values = valuesQuery.data?.values ?? [];

  return (
    <div className="space-y-2 rounded-[var(--radius-default)] border border-[var(--border-subtle)] p-3">
      <div className="flex items-center gap-2">
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">Browse values</span>
        <div className="w-[240px]">
          <Combobox
            size="sm"
            value={field ?? ''}
            onChange={setField}
            options={fields.map((f) => ({ value: f, label: f }))}
            placeholder="Pick a field"
          />
        </div>
      </div>
      {field ? (
        valuesQuery.isError ? (
          <Alert variant="warning">
            {summarizeApiErrorBody(decodeApiError(valuesQuery.error), 'Could not load values for this field.')}
          </Alert>
        ) : valuesQuery.isFetching ? (
          <p className="text-[12px] text-[var(--text-muted)]">Loading values…</p>
        ) : values.length === 0 ? (
          <p className="text-[12px] text-[var(--text-muted)]">No sample values for this field.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {values.map((v) => (
              <Badge key={v} variant="neutral" size="sm">
                {v}
              </Badge>
            ))}
          </div>
        )
      ) : (
        <p className="text-[12px] text-[var(--text-muted)]">Pick a field to see its live values from the CRM.</p>
      )}
    </div>
  );
}
