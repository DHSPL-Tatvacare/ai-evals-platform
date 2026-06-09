import { useEffect, useMemo, useState } from 'react';
import { Database } from 'lucide-react';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { LoadingState } from '@/components/ui/LoadingState';
import { Stepper, type StepperStep } from '@/components/ui/Stepper';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import type { CrmDatasetSummary } from '@/services/api/crmSource';
import {
  boundTargets,
  draftToPublishBindings,
  requiredTargets,
  useCrmMappingDraftStore,
} from '@/stores/crmMappingDraftStore';

import { CrmValueMapEditor } from '../crmMapping/CrmValueMapEditor';
import {
  useCrmDiscoveredObjects,
  useCrmFieldMap,
  useCrmGrains,
} from '../queries/crmSourceQueries';
import type { DatasetStatus } from './DatasetFooter';
import { FilterSection } from './FilterSection';
import { GoLiveSection } from './GoLiveSection';
import { MapSection } from './MapSection';
import { PreviewSection } from './PreviewSection';
import { SETUP_STEPS, useStepGating, type SetupStep } from './useStepGating';
import { useDraftAutosave } from './useDraftAutosave';

const STEP_LABELS: Record<SetupStep, string> = {
  map: 'Map',
  filter: 'Filter',
  preview: 'Preview',
  golive: 'Go live',
};

/** The selected dataset's gated setup lifecycle: hydrates the mapping draft, then drives a
 *  hard-gated, revisitable stepper (Map → Filter → Preview → Go live) over one step body. */
export function DatasetSections({
  connectionId,
  appId,
  dataset,
  onStatusChange,
}: {
  connectionId: string;
  appId: string;
  dataset: CrmDatasetSummary;
  onStatusChange: (status: DatasetStatus | null) => void;
}) {
  const [step, setStep] = useState<SetupStep>('map');
  // CRM field discovery is a live, read-only provider call — only fire it when the user asks.
  const [discoverEnabled, setDiscoverEnabled] = useState(false);

  const grainsQuery = useCrmGrains();
  const objectsQuery = useCrmDiscoveredObjects(connectionId, discoverEnabled);
  const mappingQuery = useCrmFieldMap(connectionId, dataset.recordType);

  const grain = useMemo(
    () => (grainsQuery.data?.grains ?? []).find((g) => g.recordType === dataset.recordType) ?? null,
    [grainsQuery.data, dataset.recordType],
  );
  const discovered = useMemo(
    () => (objectsQuery.data?.objects ?? []).find((o) => o.recordType === dataset.recordType) ?? null,
    [objectsQuery.data, dataset.recordType],
  );

  const startDraft = useCrmMappingDraftStore((s) => s.startDraft);
  const reset = useCrmMappingDraftStore((s) => s.reset);
  const bindings = useCrmMappingDraftStore((s) => s.bindings);
  const filterPredicate = useCrmMappingDraftStore((s) => s.filterPredicate);

  // Hydrate the draft once the grain schema and saved map are loaded for this dataset.
  useEffect(() => {
    if (grain && discovered && mappingQuery.data) {
      startDraft({
        connectionId,
        recordType: dataset.recordType,
        sourceObject: discovered.sourceObject,
        grain,
        serverBindings: mappingQuery.data.bindings,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionId, dataset.recordType, grain?.recordType, discovered?.sourceObject, mappingQuery.data]);

  useEffect(() => () => reset(), [reset]);

  const mappedFields = useMemo(
    () => Object.values(bindings).filter((b) => b.targetKind !== 'ignore').map((b) => b.semanticKey),
    [bindings],
  );
  const publishBindings = useMemo(() => draftToPublishBindings(bindings), [bindings]);
  const canActivate = useMemo(
    () => (grain ? requiredTargets(grain).every((t) => boundTargets(bindings).has(t)) : false),
    [grain, bindings],
  );

  const ready = Boolean(grain && discovered);

  const { saving, dirty } = useDraftAutosave({
    connectionId,
    recordType: dataset.recordType,
    bindings: publishBindings,
    filterPredicate,
    hydrated: ready,
  });

  const status: DatasetStatus =
    dataset.status === 'active' ? (ready && dirty ? 'active_edited' : 'active') : 'draft';

  // Surface status to the header pill — always, so it reflects the dataset even before discovery.
  useEffect(() => {
    onStatusChange(status);
  }, [status, onStatusChange]);

  const gating = useStepGating();

  // Clamp the selected step to the highest currently-unlocked step.
  useEffect(() => {
    if (!gating.unlocked[step]) setStep('map');
  }, [gating, step]);

  const steps: StepperStep<SetupStep>[] = SETUP_STEPS.map((s) => ({
    value: s,
    label: STEP_LABELS[s],
    state: s === step ? 'current' : gating.unlocked[s] ? 'done' : 'locked',
  }));

  const objectsError = objectsQuery.isError;
  const advance = NEXT_STEP[step];
  const continueButton = advance ? (
    <Button disabled={!gating.unlocked[advance.next]} onClick={() => setStep(advance.next)}>
      {advance.label}
    </Button>
  ) : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 px-6 pt-5 pb-4">
        <Stepper steps={steps} onSelect={setStep} aria-label="Dataset setup" />
      </div>

      {!grain ? (
        <LoadingState fill={false} />
      ) : (
        <>
          <div className="flex min-h-0 flex-1 flex-col px-6 pb-2">
            {step === 'map' ? (
              discovered ? (
                <MapSection
                  connectionId={connectionId}
                  recordType={dataset.recordType}
                  grain={grain}
                  fields={discovered.fields}
                  mappingLoading={mappingQuery.isLoading}
                  footerActions={continueButton}
                />
              ) : (
                <DatasetFetchPanel
                  loading={objectsQuery.isFetching}
                  error={
                    objectsError
                      ? summarizeApiErrorBody(
                          decodeApiError(objectsQuery.error),
                          'Couldn’t reach the CRM. Check the connection and try again.',
                        )
                      : null
                  }
                  onGet={() => setDiscoverEnabled(true)}
                />
              )
            ) : (
              <div className="min-h-0 flex-1 overflow-y-auto">
                {step === 'filter' ? (
                  <FilterSection
                    connectionId={connectionId}
                    recordType={dataset.recordType}
                    mappedFields={mappedFields}
                  />
                ) : null}
                {step === 'preview' ? (
                  <PreviewSection connectionId={connectionId} recordType={dataset.recordType} />
                ) : null}
                {step === 'golive' ? (
                  <GoLiveSection
                    connectionId={connectionId}
                    recordType={dataset.recordType}
                    sourceObject={dataset.sourceObject}
                    appId={appId}
                    status={status}
                    canActivate={canActivate}
                  />
                ) : null}
              </div>
            )}
          </div>

          {step !== 'map' && continueButton ? (
            <div className="flex shrink-0 items-center justify-between gap-3 border-t border-[var(--border-default)] bg-[var(--bg-primary)] px-6 py-3">
              <span className="text-[12px] text-[var(--text-muted)]">{saving ? 'Saving draft…' : ''}</span>
              {continueButton}
            </div>
          ) : null}
          <CrmValueMapEditor connectionId={connectionId} recordType={dataset.recordType} />
        </>
      )}
    </div>
  );
}

const NEXT_STEP: Record<SetupStep, { next: SetupStep; label: string } | null> = {
  map: { next: 'filter', label: 'Continue to Filter →' },
  filter: { next: 'preview', label: 'Continue to Preview →' },
  preview: { next: 'golive', label: 'Continue to Go live →' },
  golive: null,
};

/** Map-step gate: discovery is a live CRM call, so it only runs when the user clicks Get data. */
function DatasetFetchPanel({
  loading,
  error,
  onGet,
}: {
  loading: boolean;
  error: string | null;
  onGet: () => void;
}) {
  if (loading) {
    return <LoadingState fill={false} message="Fetching fields from the CRM…" />;
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--bg-secondary)]">
        <Database className="h-5 w-5 text-[var(--text-muted)]" />
      </div>
      <div className="max-w-sm space-y-1">
        <p className="text-[14px] font-medium text-[var(--text-primary)]">Get data from the CRM</p>
        <p className="text-[13px] text-[var(--text-secondary)]">
          We&rsquo;ll make a read-only call to fetch this object&rsquo;s fields so you can map them.
        </p>
      </div>
      {error ? (
        <Alert variant="error" className="max-w-sm">
          {error}
        </Alert>
      ) : null}
      <Button icon={Database} onClick={onGet}>
        Get data
      </Button>
    </div>
  );
}

