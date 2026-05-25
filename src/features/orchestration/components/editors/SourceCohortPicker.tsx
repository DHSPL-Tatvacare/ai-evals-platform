import { useMemo } from 'react';

import { Input } from '@/components/ui/Input';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { Select } from '@/components/ui/Select';
import { CohortFiltersEditor } from '@/features/orchestration/components/cohorts/CohortFiltersEditor';
import {
  InspectorField,
  InspectorSection,
} from '@/features/orchestration/components/inspector/InspectorPrimitives';
import { useCohortSources } from '@/features/orchestration/queries/cohorts';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import type { CohortColumnType } from '@/features/orchestration/types';
import { useCurrentAppId } from '@/hooks';
import type { CohortFilter } from '@/services/api/orchestrationCohorts';

import { SampleSizeField } from './SampleSizeField';
import { SavedCohortPicker } from './SavedCohortPicker';
import { SourceAndFieldsPicker } from './SourceAndFieldsPicker';

interface Props {
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}

type Mode = 'inline' | 'saved';

interface SourceCohortConfig {
  mode?: Mode;
  source_ref?: string;
  payload_fields?: string[];
  filters?: CohortFilter[];
  lookback_hours?: number | null;
  lookback_column?: string | null;
  consent_gate_channel?: string | null;
  cohort_definition_version_id?: string;
  sample_limit?: number | null;
  sample_strategy?: 'random' | 'first';
}

const MODE_OPTIONS: { value: Mode; label: string }[] = [
  { value: 'inline', label: 'Inline' },
  { value: 'saved', label: 'Saved' },
];

export function SourceCohortPicker({ value, onChange }: Props) {
  const appId = useCurrentAppId();
  const workflowType = useWorkflowBuilderStore((s) => s.workflowType);
  const cfg = value as SourceCohortConfig;
  const mode: Mode = cfg.mode === 'saved' ? 'saved' : 'inline';

  const { data: sources = [] } = useCohortSources(workflowType, appId);
  const selectedSource = useMemo(
    () => sources.find((s) => s.sourceRef === cfg.source_ref),
    [sources, cfg.source_ref],
  );

  const lookbackColumnOptions = useMemo(
    () => [
      { value: '', label: 'None' },
      ...(selectedSource?.allowedLookbackColumns ?? []).map((c) => ({
        value: c,
        label: c,
      })),
    ],
    [selectedSource],
  );

  // Build a name→type map from the source's schema descriptor for the filter editor.
  const columnTypes = useMemo((): Record<string, CohortColumnType> => {
    const cols = selectedSource?.schemaDescriptor?.columns ?? [];
    return Object.fromEntries(cols.map((c) => [c.name, c.type]));
  }, [selectedSource]);

  function setMode(next: Mode) {
    // Always carry mode; preserve the per-mode slice each branch owns so a
    // mistaken toggle doesn't wipe a half-built config.
    onChange({ ...value, mode: next });
  }

  function setSourceAndFields(next: {
    source_ref?: string;
    payload_fields: string[];
  }) {
    onChange({ ...value, mode: 'inline', ...next });
  }

  function setFilters(filters: CohortFilter[]) {
    onChange({ ...value, mode: 'inline', filters });
  }

  function setLookbackHours(raw: string) {
    const trimmed = raw.trim();
    const next = trimmed === '' ? null : Number(trimmed);
    onChange({
      ...value,
      mode: 'inline',
      lookback_hours: Number.isFinite(next as number) ? next : null,
    });
  }

  function setLookbackColumn(column: string) {
    onChange({ ...value, mode: 'inline', lookback_column: column || null });
  }

  function setConsentChannel(raw: string) {
    onChange({
      ...value,
      mode: 'inline',
      consent_gate_channel: raw.trim() || null,
    });
  }

  function setSample(next: { limit: number | null; strategy: 'random' | 'first' }) {
    onChange({
      ...value,
      sample_limit: next.limit,
      sample_strategy: next.strategy,
    });
  }

  return (
    <InspectorSection
      title="Audience"
      description="Choose a live source to query each run, or pin a saved cohort."
    >
      <InspectorField label="Mode">
        <SegmentedControl<Mode>
          options={MODE_OPTIONS}
          value={mode}
          onChange={setMode}
          aria-label="Audience source mode"
        />
      </InspectorField>

      {mode === 'inline' ? (
        <>
          <SourceAndFieldsPicker
            value={{
              source_ref: cfg.source_ref,
              payload_fields: cfg.payload_fields ?? [],
            }}
            onChange={setSourceAndFields}
            workflowType={workflowType}
            appId={appId}
          />
          <InspectorField
            label="Filters"
            description="Narrow the audience to contacts that match every filter."
          >
            <CohortFiltersEditor
              value={cfg.filters ?? []}
              onChange={setFilters}
              columnOptions={cfg.payload_fields ?? []}
              columnTypes={columnTypes}
              sourceRef={cfg.source_ref}
              appId={appId ?? undefined}
            />
          </InspectorField>
          <InspectorField
            label="Lookback (hours)"
            description="Only include rows touched within this window. Leave blank for no window."
          >
            <Input
              type="number"
              value={cfg.lookback_hours == null ? '' : String(cfg.lookback_hours)}
              onChange={(e) => setLookbackHours(e.target.value)}
              placeholder="no window"
            />
          </InspectorField>
          {selectedSource &&
          (selectedSource.allowedLookbackColumns ?? []).length > 0 ? (
            <InspectorField
              label="Lookback column"
              description="Timestamp column the lookback window is measured against."
            >
              <Select
                value={cfg.lookback_column ?? ''}
                onChange={setLookbackColumn}
                options={lookbackColumnOptions}
                placeholder="None"
              />
            </InspectorField>
          ) : null}
          <InspectorField
            label="Consent gate channel"
            description="Drop contacts without consent for this channel. Leave blank to skip."
          >
            <Input
              value={cfg.consent_gate_channel ?? ''}
              onChange={(e) => setConsentChannel(e.target.value)}
              placeholder="e.g. wa"
            />
          </InspectorField>
        </>
      ) : (
        <SavedCohortPicker
          value={value}
          onChange={(next) => onChange({ ...next, mode: 'saved' })}
        />
      )}
      <SampleSizeField
        limit={cfg.sample_limit ?? null}
        strategy={cfg.sample_strategy ?? 'random'}
        onChange={setSample}
      />
    </InspectorSection>
  );
}
