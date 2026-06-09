import { useEffect, useRef, useState } from 'react';

import type { CrmDatasetDraftBody, CrmFieldBinding } from '@/services/api/crmSource';
import type { PredicateAst } from '@/features/orchestration/types';

import { useSaveDraft } from '../queries/crmSourceQueries';

const DEBOUNCE_MS = 800;

function snapshot(bindings: CrmFieldBinding[], predicate: PredicateAst | undefined): string {
  return JSON.stringify({ bindings, predicate: predicate ?? null });
}

/** Debounce-persists the draft (bindings + filter) on change. Returns `saving` and `dirty`
 *  (the draft diverges from the snapshot captured when the dataset was hydrated). The first
 *  change after hydration arms autosave; the hydration snapshot itself never persists. */
export function useDraftAutosave({
  connectionId,
  recordType,
  bindings,
  filterPredicate,
  hydrated,
}: {
  connectionId: string;
  recordType: string;
  bindings: CrmFieldBinding[];
  filterPredicate: PredicateAst | undefined;
  hydrated: boolean;
}): { saving: boolean; dirty: boolean } {
  const saveDraft = useSaveDraft(connectionId);
  const baselineRef = useRef<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const current = snapshot(bindings, filterPredicate);

  // Capture the baseline once the dataset hydrates; resets when the dataset switches.
  useEffect(() => {
    baselineRef.current = null;
    setDirty(false);
  }, [connectionId, recordType]);

  useEffect(() => {
    if (!hydrated) return;
    if (baselineRef.current === null) {
      baselineRef.current = current;
      return;
    }
    if (current === baselineRef.current) {
      setDirty(false);
      return;
    }
    setDirty(true);
    const body: CrmDatasetDraftBody = {
      recordType,
      bindings,
      filterPredicate: (filterPredicate as Record<string, unknown> | undefined) ?? null,
    };
    const handle = setTimeout(() => saveDraft.mutate(body), DEBOUNCE_MS);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, hydrated]);

  return { saving: saveDraft.isPending, dirty };
}
