import { useState, type ReactNode } from 'react';
import { FlaskConical } from 'lucide-react';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import type { CrmGrainSchema } from '@/services/api/crmSource';
import { boundTargets, requiredTargets, useCrmMappingDraftStore } from '@/stores/crmMappingDraftStore';

import { MappingFieldsTable } from '../crmMapping/MappingFieldsTable';
import { SampleDataOverlay } from './SampleDataOverlay';

function grainLabel(grain: CrmGrainSchema, target: string): string {
  return grain.standardColumns.find((c) => c.target === target)?.label ?? target;
}

/** Step 1 — map the CRM's fields, full height. A Sample data button opens a reference overlay. */
export function MapSection({
  connectionId,
  recordType,
  grain,
  fields,
  mappingLoading,
  footerActions,
}: {
  connectionId: string;
  recordType: string;
  grain: CrmGrainSchema;
  fields: string[];
  mappingLoading: boolean;
  footerActions?: ReactNode;
}) {
  const bindings = useCrmMappingDraftStore((s) => s.bindings);
  const [sampleOpen, setSampleOpen] = useState(false);

  const bound = boundTargets(bindings);
  const missingRequired = requiredTargets(grain).filter((t) => !bound.has(t));

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {missingRequired.length > 0 ? (
        <Alert variant="warning">
          Map {missingRequired.map((t) => grainLabel(grain, t)).join(', ')} before publishing — without it
          rows can&rsquo;t be linked.
        </Alert>
      ) : null}
      <MappingFieldsTable
        grain={grain}
        fields={fields}
        boundCount={bound.size}
        loading={mappingLoading}
        headerActions={
          <Button variant="secondary" size="sm" icon={FlaskConical} onClick={() => setSampleOpen(true)}>
            Sample data
          </Button>
        }
        footerActions={footerActions}
      />
      {sampleOpen ? (
        <SampleDataOverlay
          connectionId={connectionId}
          recordType={recordType}
          onClose={() => setSampleOpen(false)}
        />
      ) : null}
    </div>
  );
}
