import { useEffect, useMemo, useState } from 'react';

import { Alert } from '@/components/ui/Alert';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
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
import { DatasetFooter, type DatasetStatus } from './DatasetFooter';
import { FilterSection } from './FilterSection';
import { MapSection } from './MapSection';
import { PreviewSection } from './PreviewSection';
import { ScheduleSection } from './ScheduleSection';
import { useDraftAutosave } from './useDraftAutosave';

type DatasetView = 'map' | 'filter' | 'preview';

const VIEW_OPTIONS: { value: DatasetView; label: string }[] = [
  { value: 'map', label: 'Map fields' },
  { value: 'filter', label: 'Filter' },
  { value: 'preview', label: 'Preview' },
];

/** The selected dataset's lifecycle sections. Hydrates the mapping draft from the grain
 *  schema, discovered fields, and any saved bindings, then renders Map / Filter / Preview,
 *  a recurring schedule, and the run-control footer. */
export function DatasetSections({
  connectionId,
  dataset,
}: {
  connectionId: string;
  dataset: CrmDatasetSummary;
}) {
  const [view, setView] = useState<DatasetView>('map');

  const grainsQuery = useCrmGrains();
  const objectsQuery = useCrmDiscoveredObjects(connectionId, true);
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

  const ready = Boolean(grain && discovered);
  const missingRequired = requiredTargets(grain).filter((t) => !boundTargets(bindings).has(t));
  const canActivate = ready && missingRequired.length === 0;

  const { saving, dirty } = useDraftAutosave({
    connectionId,
    recordType: dataset.recordType,
    bindings: publishBindings,
    filterPredicate,
    hydrated: ready,
  });

  const status: DatasetStatus =
    dataset.status === 'active' ? (dirty ? 'active_edited' : 'active') : 'draft';

  const objectsError = objectsQuery.isError;

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <SegmentedControl options={VIEW_OPTIONS} value={view} onChange={setView} aria-label="Dataset section" />

        {objectsError ? (
          <Alert variant="error" title="Couldn&rsquo;t reach the CRM">
            {summarizeApiErrorBody(decodeApiError(objectsQuery.error), 'Check the connection credentials and try again.')}
          </Alert>
        ) : !ready ? (
          <p className="text-[13px] text-[var(--text-secondary)]">Loading dataset…</p>
        ) : (
          <>
            {view === 'map' && grain && discovered ? (
              <MapSection
                connectionId={connectionId}
                recordType={dataset.recordType}
                grain={grain}
                fields={discovered.fields}
                mappingLoading={mappingQuery.isLoading}
              />
            ) : null}
            {view === 'filter' ? (
              <FilterSection
                connectionId={connectionId}
                recordType={dataset.recordType}
                mappedFields={mappedFields}
              />
            ) : null}
            {view === 'preview' ? (
              <PreviewSection connectionId={connectionId} recordType={dataset.recordType} />
            ) : null}
          </>
        )}
      </div>

      {ready && discovered ? (
        <>
          <ScheduleSection connectionId={connectionId} sourceObject={discovered.sourceObject} />
          <DatasetFooter
            connectionId={connectionId}
            recordType={dataset.recordType}
            sourceObject={discovered.sourceObject}
            status={status}
            version={dataset.version}
            canActivate={canActivate}
            saving={saving}
            lastSyncAt={dataset.lastSyncAt}
          />
          <CrmValueMapEditor connectionId={connectionId} recordType={dataset.recordType} />
        </>
      ) : null}
    </div>
  );
}
