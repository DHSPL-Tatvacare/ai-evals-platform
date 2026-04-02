import { create } from 'zustand';
import type { AssetVisibility, EvaluatorDefinition, EvaluatorVisibilityFilter } from '@/types';
import { evaluatorsRepository } from '@/services/storage';
import { filterEvaluatorsByVisibility } from '@/services/api/evaluatorsApi';

interface EvaluatorsStore {
  evaluators: EvaluatorDefinition[];
  isLoaded: boolean;
  currentListingId: string | null;
  currentAppId: string | null;

  sharedEvaluators: EvaluatorDefinition[];
  isSharedLoaded: boolean;
  currentSharedAppId: string | null;

  // Legacy alias for shared-evaluator state until Phase 6 UI cutover
  registry: EvaluatorDefinition[];
  isRegistryLoaded: boolean;
  currentRegistryAppId: string | null;

  loadEvaluators: (appId: string, listingId: string) => Promise<void>;
  loadAppEvaluators: (appId: string) => Promise<void>;
  loadSharedEvaluators: (appId: string) => Promise<void>;
  loadRegistry: (appId: string) => Promise<void>;
  getEvaluatorsByVisibility: (visibility: AssetVisibility) => EvaluatorDefinition[];
  getEvaluatorsByFilter: (filter: EvaluatorVisibilityFilter) => EvaluatorDefinition[];
  addEvaluator: (evaluator: EvaluatorDefinition) => Promise<void>;
  updateEvaluator: (evaluator: EvaluatorDefinition) => Promise<void>;
  deleteEvaluator: (id: string) => Promise<void>;
  setVisibility: (id: string, visibility: AssetVisibility) => Promise<void>;
  setGlobal: (id: string, isGlobal: boolean) => Promise<void>;
  setBuiltIn: (id: string, isBuiltIn: boolean) => Promise<void>;
  forkEvaluator: (sourceId: string, targetListingId?: string) => Promise<EvaluatorDefinition>;
  seedDefaults: (listingId: string) => Promise<EvaluatorDefinition[]>;
  seedAppDefaults: (appId: string) => Promise<EvaluatorDefinition[]>;
  reset: () => void;
}

// Track in-flight fetch to deduplicate parallel calls
let _loadingListingId: string | null = null;

function replaceById<T extends { id: string }>(items: T[], item: T): T[] {
  const index = items.findIndex((entry) => entry.id === item.id);
  if (index === -1) {
    return [...items, item];
  }
  return items.map((entry) => (entry.id === item.id ? item : entry));
}

function removeById<T extends { id: string }>(items: T[], id: string): T[] {
  return items.filter((item) => item.id !== id);
}

function upsertEvaluatorState(
  state: Pick<EvaluatorsStore, 'evaluators' | 'sharedEvaluators' | 'registry'>,
  evaluator: EvaluatorDefinition,
) {
  const nextEvaluators = replaceById(state.evaluators, evaluator);
  const nextShared = (evaluator.visibility ?? 'private') === 'app'
    ? replaceById(state.sharedEvaluators, evaluator)
    : removeById(state.sharedEvaluators, evaluator.id);

  return {
    evaluators: nextEvaluators,
    sharedEvaluators: nextShared,
    registry: nextShared,
  };
}

export const useEvaluatorsStore = create<EvaluatorsStore>((set, get) => ({
  evaluators: [],
  isLoaded: false,
  currentListingId: null,
  currentAppId: null,
  sharedEvaluators: [],
  isSharedLoaded: false,
  currentSharedAppId: null,
  registry: [],
  isRegistryLoaded: false,
  currentRegistryAppId: null,

  loadEvaluators: async (appId: string, listingId: string) => {
    const { currentListingId, isLoaded } = get();

    // Skip if already loaded for this listing or a fetch is in-flight for it
    if ((isLoaded && currentListingId === listingId) || _loadingListingId === listingId) {
      return;
    }

    _loadingListingId = listingId;
    set({ isLoaded: false });

    try {
      const evaluators = await evaluatorsRepository.getForListing(appId, listingId);
      set({ evaluators, isLoaded: true, currentListingId: listingId, currentAppId: appId });
    } finally {
      if (_loadingListingId === listingId) {
        _loadingListingId = null;
      }
    }
  },

  loadAppEvaluators: async (appId: string) => {
    const { currentAppId, currentListingId } = get();
    if (currentAppId !== appId || currentListingId !== null) {
      set({ isLoaded: false });
    }

    const evaluators = await evaluatorsRepository.getByAppId(appId);
    set({ evaluators, isLoaded: true, currentListingId: null, currentAppId: appId });
  },

  loadSharedEvaluators: async (appId: string) => {
    const sharedEvaluators = await evaluatorsRepository.getShared(appId);
    set({
      sharedEvaluators,
      isSharedLoaded: true,
      currentSharedAppId: appId,
      registry: sharedEvaluators,
      isRegistryLoaded: true,
      currentRegistryAppId: appId,
    });
  },

  loadRegistry: async (appId: string) => {
    await get().loadSharedEvaluators(appId);
  },

  getEvaluatorsByVisibility: (visibility: AssetVisibility) => {
    return get().evaluators.filter((evaluator) => (evaluator.visibility ?? 'private') === visibility);
  },

  getEvaluatorsByFilter: (filter: EvaluatorVisibilityFilter) => {
    return filterEvaluatorsByVisibility(get().evaluators, filter);
  },
  
  addEvaluator: async (evaluator: EvaluatorDefinition) => {
    const saved = await evaluatorsRepository.save(evaluator);
    set((state) => upsertEvaluatorState(state, saved));
  },

  updateEvaluator: async (evaluator: EvaluatorDefinition) => {
    const saved = await evaluatorsRepository.save(evaluator);
    set((state) => upsertEvaluatorState(state, saved));
  },
  
  deleteEvaluator: async (id: string) => {
    await evaluatorsRepository.delete(id);
    set((state) => ({
      evaluators: removeById(state.evaluators, id),
      sharedEvaluators: removeById(state.sharedEvaluators, id),
      registry: removeById(state.registry, id),
    }));
  },

  setVisibility: async (id: string, visibility: AssetVisibility) => {
    const updated = await evaluatorsRepository.setVisibility(id, visibility);
    set((state) => ({
      evaluators: replaceById(state.evaluators, updated),
      sharedEvaluators: visibility === 'app'
        ? replaceById(state.sharedEvaluators, updated)
        : removeById(state.sharedEvaluators, id),
      registry: visibility === 'app'
        ? replaceById(state.registry, updated)
        : removeById(state.registry, id),
    }));
  },

  setGlobal: async (id: string, isGlobal: boolean) => {
    await get().setVisibility(id, isGlobal ? 'app' : 'private');
  },

  setBuiltIn: async () => {
    throw new Error('Built-in status is managed by system defaults and cannot be changed');
  },
  
  forkEvaluator: async (sourceId: string, targetListingId?: string) => {
    const forked = await evaluatorsRepository.fork(sourceId, targetListingId);
    set((state) => upsertEvaluatorState(state, forked));
    return forked;
  },

  seedDefaults: async (listingId: string) => {
    const seeded = await evaluatorsRepository.seedDefaults(listingId);
    set((state) => ({
      evaluators: seeded.reduce((items, item) => replaceById(items, item), state.evaluators),
      sharedEvaluators: seeded.reduce(
        (items, item) => (
          (item.visibility ?? 'private') === 'app'
            ? replaceById(items, item)
            : removeById(items, item.id)
        ),
        state.sharedEvaluators,
      ),
      registry: seeded.reduce(
        (items, item) => (
          (item.visibility ?? 'private') === 'app'
            ? replaceById(items, item)
            : removeById(items, item.id)
        ),
        state.registry,
      ),
    }));
    return seeded;
  },

  seedAppDefaults: async (appId: string) => {
    const seeded = await evaluatorsRepository.seedAppDefaults(appId);
    set((state) => ({
      evaluators: seeded.reduce((items, item) => replaceById(items, item), state.evaluators),
      sharedEvaluators: seeded.reduce(
        (items, item) => (
          (item.visibility ?? 'private') === 'app'
            ? replaceById(items, item)
            : removeById(items, item.id)
        ),
        state.sharedEvaluators,
      ),
      registry: seeded.reduce(
        (items, item) => (
          (item.visibility ?? 'private') === 'app'
            ? replaceById(items, item)
            : removeById(items, item.id)
        ),
        state.registry,
      ),
    }));
    return seeded;
  },

  reset: () => {
    _loadingListingId = null;
    set({
      evaluators: [],
      isLoaded: false,
      currentListingId: null,
      currentAppId: null,
      sharedEvaluators: [],
      isSharedLoaded: false,
      currentSharedAppId: null,
      registry: [],
      isRegistryLoaded: false,
      currentRegistryAppId: null,
    });
  },
}));
