import { useState } from 'react';

import { Alert } from '@/components/ui/Alert';
import type { CrmFieldBinding, CrmGrainSchema } from '@/services/api/crmSource';
import {
  boundTargets,
  draftToPublishBindings,
  requiredTargets,
  useCrmMappingDraftStore,
} from '@/stores/crmMappingDraftStore';

import { MappingFieldsTable } from '../crmMapping/MappingFieldsTable';
import { SampleToggle } from './SampleToggle';

type SampleView = 'raw' | 'unpacked';

function grainLabel(grain: CrmGrainSchema, target: string): string {
  return grain.standardColumns.find((c) => c.target === target)?.label ?? target;
}

/** Step 1 — map the CRM's fields plus a raw/unpacked sample for immediate guidance. */
export function MapSection({
  connectionId,
  recordType,
  grain,
  fields,
  mappingLoading,
}: {
  connectionId: string;
  recordType: string;
  grain: CrmGrainSchema;
  fields: string[];
  mappingLoading: boolean;
}) {
  const bindings = useCrmMappingDraftStore((s) => s.bindings);
  const [sampleView, setSampleView] = useState<SampleView>('raw');

  const bound = boundTargets(bindings);
  const missingRequired = requiredTargets(grain).filter((t) => !bound.has(t));
  const publishBindings: CrmFieldBinding[] = draftToPublishBindings(bindings);

  return (
    <div className="space-y-4">
      {missingRequired.length > 0 ? (
        <Alert variant="warning">
          Map {missingRequired.map((t) => grainLabel(grain, t)).join(', ')} before publishing — without it
          rows can&rsquo;t be linked.
        </Alert>
      ) : null}
      <SampleToggle
        connectionId={connectionId}
        recordType={recordType}
        bindings={publishBindings}
        view={sampleView}
        onViewChange={setSampleView}
      />
      <MappingFieldsTable grain={grain} fields={fields} boundCount={bound.size} loading={mappingLoading} />
    </div>
  );
}
