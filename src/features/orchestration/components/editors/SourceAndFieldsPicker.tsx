import { useMemo } from 'react';

import { Combobox } from '@/components/ui/Combobox';
import {
  InspectorEmptyState,
  InspectorField,
} from '@/features/orchestration/components/inspector/InspectorPrimitives';
import { useCohortSources } from '@/features/orchestration/queries/cohorts';
import type { CohortSource, WorkflowType } from '@/features/orchestration/types';

interface SourceAndFieldsValue {
  source_ref?: string;
  payload_fields: string[];
}

interface Props {
  value: SourceAndFieldsValue;
  onChange: (next: SourceAndFieldsValue) => void;
  workflowType: WorkflowType | null | undefined;
  appId: string | null | undefined;
  disabled?: boolean;
}

function fieldOptionsFor(source: CohortSource | undefined): string[] {
  if (!source) return [];
  const fromCatalog = source.allowedPayloadColumns ?? [];
  const fromSchema = source.schemaDescriptor?.columns.map((c) => c.name) ?? [];
  return Array.from(new Set([...fromCatalog, ...fromSchema]));
}

export function SourceAndFieldsPicker({
  value,
  onChange,
  workflowType,
  appId,
  disabled,
}: Props) {
  const { data: sources = [] } = useCohortSources(workflowType, appId);

  const sourceOptions = useMemo(
    () =>
      sources.map((s) => ({
        value: s.sourceRef,
        label: s.displayLabel,
        description: s.description,
      })),
    [sources],
  );

  const selectedSource = useMemo(
    () => sources.find((s) => s.sourceRef === value.source_ref),
    [sources, value.source_ref],
  );

  const fieldOptions = useMemo(
    () => fieldOptionsFor(selectedSource).map((c) => ({ value: c, label: c })),
    [selectedSource],
  );

  function setSource(sourceRef: string) {
    // Switching source invalidates field selection — the new source owns a
    // different column set, so stale fields would fail the catalog check.
    onChange({ source_ref: sourceRef, payload_fields: [] });
  }

  function setFields(fields: string[]) {
    onChange({ ...value, payload_fields: fields });
  }

  if (sources.length === 0) {
    return (
      <InspectorField label="Source">
        <InspectorEmptyState>
          No sources available for this workflow yet.
        </InspectorEmptyState>
      </InspectorField>
    );
  }

  return (
    <>
      <InspectorField
        label="Source"
        description="The live table or dataset this step queries on every run."
      >
        <Combobox
          value={value.source_ref ?? ''}
          onChange={setSource}
          options={sourceOptions}
          placeholder="Pick a source…"
          disabled={disabled}
        />
      </InspectorField>
      {value.source_ref ? (
        <InspectorField
          label="Fields"
          description="Columns carried into the workflow payload for each contact."
        >
          <Combobox
            multi
            value={value.payload_fields}
            onChange={setFields}
            options={fieldOptions}
            placeholder="Pick fields…"
            disabled={disabled}
          />
        </InspectorField>
      ) : null}
    </>
  );
}
