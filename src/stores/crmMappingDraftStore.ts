// client-only: in-progress CRM mapping draft (bindings / value-maps / selected object) before
// Publish. Server truth (discovered fields, published map, sync activity) lives in
// crmSourceQueries. Not a query — it's a multi-step form draft, the reviewModeStore precedent.
import { create } from 'zustand';

import type { CrmFieldBinding, CrmGrainSchema } from '@/services/api/crmSource';
import type { PredicateAst } from '@/features/orchestration/types';

export type CrmTargetKind = 'standard' | 'slot' | 'ignore';

/** Slot-pool type (grain.slots key) → the data_type the unpacker coerces by. */
const SLOT_DATA_TYPE: Record<string, string> = {
  text: 'text',
  int: 'int',
  num: 'num',
  dt: 'datetime',
  bool: 'bool',
  json: 'json',
};

/** Slot column prefix → slot-pool type (the inverse used to read a bound slot's type back). */
const SLOT_PREFIX_TYPE: Record<string, string> = {
  txt: 'text',
  int: 'int',
  num: 'num',
  dt: 'dt',
  bool: 'bool',
  json: 'json',
};

export function slotTypeOf(slotName: string): string | null {
  return SLOT_PREFIX_TYPE[slotName.split('_')[0]] ?? null;
}

export interface CrmBindingDraft {
  sourceField: string;
  targetKind: CrmTargetKind;
  /** standard column name, allocated slot name, or '' for ignore. */
  target: string;
  semanticKey: string;
  dataType: string;
  valueMap: Record<string, string> | null;
}

interface CrmMappingDraftState {
  connectionId: string | null;
  recordType: string | null;
  sourceObject: string | null;
  grain: CrmGrainSchema | null;
  bindings: Record<string, CrmBindingDraft>;
  valueMapField: string | null;
  /** Optional row-level filter over the mapped fields; undefined = no filter. */
  filterPredicate: PredicateAst | undefined;

  startDraft(input: {
    connectionId: string;
    recordType: string;
    sourceObject: string;
    grain: CrmGrainSchema;
    serverBindings: CrmFieldBinding[];
  }): void;
  setTargetStandard(sourceField: string, column: { target: string; label: string; dataType: string }): void;
  setTargetSlot(sourceField: string, slotType: string): void;
  setIgnore(sourceField: string): void;
  setSemanticKey(sourceField: string, value: string): void;
  setValueMap(sourceField: string, valueMap: Record<string, string> | null): void;
  openValueMap(sourceField: string): void;
  closeValueMap(): void;
  setFilterPredicate(predicate: PredicateAst | undefined): void;
  reset(): void;
}

function usedSlotNames(bindings: Record<string, CrmBindingDraft>, exceptField: string): Set<string> {
  const used = new Set<string>();
  for (const [field, b] of Object.entries(bindings)) {
    if (field !== exceptField && b.targetKind === 'slot' && b.target) used.add(b.target);
  }
  return used;
}

function nextFreeSlot(grain: CrmGrainSchema, slotType: string, used: Set<string>): string | null {
  const pool = grain.slots[slotType] ?? [];
  return pool.find((s) => !used.has(s)) ?? null;
}

export const useCrmMappingDraftStore = create<CrmMappingDraftState>()((set, get) => ({
  connectionId: null,
  recordType: null,
  sourceObject: null,
  grain: null,
  bindings: {},
  valueMapField: null,
  filterPredicate: undefined,

  startDraft: ({ connectionId, recordType, sourceObject, grain, serverBindings }) => {
    const standardTargets = new Set(grain.standardColumns.map((c) => c.target));
    const bindings: Record<string, CrmBindingDraft> = {};
    for (const b of serverBindings) {
      bindings[b.sourceField] = {
        sourceField: b.sourceField,
        targetKind: standardTargets.has(b.slot) ? 'standard' : 'slot',
        target: b.slot,
        semanticKey: b.semanticKey,
        dataType: b.dataType,
        valueMap: b.valueMap,
      };
    }
    set({ connectionId, recordType, sourceObject, grain, bindings, valueMapField: null, filterPredicate: undefined });
  },

  setTargetStandard: (sourceField, column) => {
    set((state) => ({
      bindings: {
        ...state.bindings,
        [sourceField]: {
          sourceField,
          targetKind: 'standard',
          target: column.target,
          semanticKey: column.label,
          dataType: column.dataType,
          valueMap: state.bindings[sourceField]?.valueMap ?? null,
        },
      },
    }));
  },

  setTargetSlot: (sourceField, slotType) => {
    const { grain, bindings } = get();
    if (!grain) return;
    const current = bindings[sourceField];
    // Already on a slot of this type → keep the allocated slot, don't churn the pool.
    if (current?.targetKind === 'slot' && slotTypeOf(current.target) === slotType) return;
    const used = usedSlotNames(bindings, sourceField);
    const slot = nextFreeSlot(grain, slotType, used);
    if (!slot) return; // pool exhausted — the row stays unbound; UI surfaces the limit
    set((state) => ({
      bindings: {
        ...state.bindings,
        [sourceField]: {
          sourceField,
          targetKind: 'slot',
          target: slot,
          semanticKey: state.bindings[sourceField]?.semanticKey || sourceField,
          dataType: SLOT_DATA_TYPE[slotType] ?? 'text',
          valueMap: state.bindings[sourceField]?.valueMap ?? null,
        },
      },
    }));
  },

  setIgnore: (sourceField) => {
    set((state) => {
      const next = { ...state.bindings };
      delete next[sourceField];
      return { bindings: next };
    });
  },

  setSemanticKey: (sourceField, value) => {
    set((state) => {
      const b = state.bindings[sourceField];
      if (!b) return {};
      return { bindings: { ...state.bindings, [sourceField]: { ...b, semanticKey: value } } };
    });
  },

  setValueMap: (sourceField, valueMap) => {
    set((state) => {
      const b = state.bindings[sourceField];
      if (!b) return {};
      return { bindings: { ...state.bindings, [sourceField]: { ...b, valueMap } } };
    });
  },

  openValueMap: (sourceField) => set({ valueMapField: sourceField }),
  closeValueMap: () => set({ valueMapField: null }),

  setFilterPredicate: (predicate) => set({ filterPredicate: predicate }),

  reset: () =>
    set({
      connectionId: null,
      recordType: null,
      sourceObject: null,
      grain: null,
      bindings: {},
      valueMapField: null,
      filterPredicate: undefined,
    }),
}));

/** Build the publish payload from the draft — non-ignored bindings only. */
export function draftToPublishBindings(bindings: Record<string, CrmBindingDraft>): CrmFieldBinding[] {
  return Object.values(bindings)
    .filter((b) => b.targetKind !== 'ignore' && b.target)
    .map((b) => ({
      slot: b.target,
      semanticKey: b.semanticKey || b.sourceField,
      sourceField: b.sourceField,
      dataType: b.dataType,
      valueMap: b.valueMap,
    }));
}

/** The required targets that must be bound before publish (natural key + lead-link). */
export function requiredTargets(grain: CrmGrainSchema | null): string[] {
  if (!grain) return [];
  const req = [grain.naturalKeyTarget];
  if (grain.leadLinkRequired) req.push(grain.leadLinkTarget);
  return req;
}

/** Targets currently bound (non-ignore). */
export function boundTargets(bindings: Record<string, CrmBindingDraft>): Set<string> {
  return new Set(
    Object.values(bindings)
      .filter((b) => b.targetKind !== 'ignore' && b.target)
      .map((b) => b.target),
  );
}
