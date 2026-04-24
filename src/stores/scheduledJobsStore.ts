import { create } from 'zustand';
import { scheduledJobsApi } from '@/services/api/scheduledJobsApi';
import type {
  Schedule,
  ScheduleCreateInput,
  ScheduleFireSummary,
  ScheduleRegistryResponse,
  ScheduleUpdateInput,
} from '@/features/admin/scheduledJobs/types';

interface DetailEntry {
  fires: ScheduleFireSummary[];
  loading: boolean;
  error: string | null;
  loadedAt: number | null;
}

interface ScheduledJobsState {
  schedules: Schedule[];
  isLoading: boolean;
  error: string | null;
  registry: ScheduleRegistryResponse | null;
  registryLoading: boolean;
  /** Per-schedule detail cache keyed by schedule id. Surfaces the fires list
   *  for the history overlay without re-fetching on every open. */
  detailById: Record<string, DetailEntry>;

  load: () => Promise<void>;
  loadRegistry: () => Promise<void>;
  create: (payload: ScheduleCreateInput) => Promise<Schedule>;
  update: (id: string, payload: ScheduleUpdateInput) => Promise<Schedule>;
  remove: (id: string) => Promise<void>;
  toggle: (id: string) => Promise<Schedule>;
  fireNow: (id: string) => Promise<Schedule>;
  fetchDetail: (id: string) => Promise<void>;
  reset: () => void;
}

export const useScheduledJobsStore = create<ScheduledJobsState>((set, get) => ({
  schedules: [],
  isLoading: false,
  error: null,
  registry: null,
  registryLoading: false,
  detailById: {},

  load: async () => {
    set({ isLoading: true, error: null });
    try {
      const schedules = await scheduledJobsApi.list();
      set({ schedules, isLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load schedules';
      set({ error: msg, isLoading: false });
    }
  },

  loadRegistry: async () => {
    if (get().registry || get().registryLoading) return;
    set({ registryLoading: true });
    try {
      const registry = await scheduledJobsApi.registry();
      set({ registry, registryLoading: false });
    } catch {
      set({ registryLoading: false });
    }
  },

  create: async (payload) => {
    const created = await scheduledJobsApi.create(payload);
    set((s) => ({ schedules: [created, ...s.schedules] }));
    return created;
  },

  update: async (id, payload) => {
    const updated = await scheduledJobsApi.update(id, payload);
    set((s) => ({
      schedules: s.schedules.map((sch) => (sch.id === id ? updated : sch)),
    }));
    return updated;
  },

  remove: async (id) => {
    await scheduledJobsApi.remove(id);
    set((s) => ({ schedules: s.schedules.filter((sch) => sch.id !== id) }));
  },

  toggle: async (id) => {
    const updated = await scheduledJobsApi.toggle(id);
    set((s) => ({
      schedules: s.schedules.map((sch) => (sch.id === id ? updated : sch)),
    }));
    return updated;
  },

  fireNow: async (id) => {
    const updated = await scheduledJobsApi.fireNow(id);
    set((s) => ({
      schedules: s.schedules.map((sch) => (sch.id === id ? updated : sch)),
    }));
    return updated;
  },

  fetchDetail: async (id) => {
    set((s) => ({
      detailById: {
        ...s.detailById,
        [id]: {
          fires: s.detailById[id]?.fires ?? [],
          loading: true,
          error: null,
          loadedAt: s.detailById[id]?.loadedAt ?? null,
        },
      },
    }));
    try {
      const detail = await scheduledJobsApi.get(id);
      set((s) => ({
        detailById: {
          ...s.detailById,
          [id]: {
            fires: detail.recentFires,
            loading: false,
            error: null,
            loadedAt: Date.now(),
          },
        },
      }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load run history';
      set((s) => ({
        detailById: {
          ...s.detailById,
          [id]: {
            fires: s.detailById[id]?.fires ?? [],
            loading: false,
            error: msg,
            loadedAt: s.detailById[id]?.loadedAt ?? null,
          },
        },
      }));
    }
  },

  reset: () =>
    set({
      schedules: [],
      isLoading: false,
      error: null,
      registry: null,
      registryLoading: false,
      detailById: {},
    }),
}));
