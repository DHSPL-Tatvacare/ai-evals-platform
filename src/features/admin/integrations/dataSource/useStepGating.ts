import { boundTargets, requiredTargets, useCrmMappingDraftStore } from '@/stores/crmMappingDraftStore';

export type SetupStep = 'map' | 'filter' | 'preview' | 'golive';

export const SETUP_STEPS: SetupStep[] = ['map', 'filter', 'preview', 'golive'];

export interface StepGating {
  mapValid: boolean;
  hasFilter: boolean;
  /** Which steps are unlocked. Map is always unlocked. */
  unlocked: Record<SetupStep, boolean>;
}

/** Derives hard-gating from the live draft: Map valid when required targets are bound;
 *  Filter unlocks on a valid Map; Preview unlocks on a valid Map; Go live unlocks when
 *  Map (and Filter, if a predicate is set) is valid. */
export function useStepGating(): StepGating {
  const grain = useCrmMappingDraftStore((s) => s.grain);
  const bindings = useCrmMappingDraftStore((s) => s.bindings);
  const filterPredicate = useCrmMappingDraftStore((s) => s.filterPredicate);

  const bound = boundTargets(bindings);
  const mapValid = grain !== null && requiredTargets(grain).every((t) => bound.has(t));
  const hasFilter = filterPredicate !== undefined;

  return {
    mapValid,
    hasFilter,
    unlocked: {
      map: true,
      filter: mapValid,
      preview: mapValid,
      golive: mapValid,
    },
  };
}
