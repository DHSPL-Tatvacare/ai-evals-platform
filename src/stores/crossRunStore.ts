import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AppId } from '@/types';
import { reportsApi } from '@/services/api/reportsApi';
import { ApiError } from '@/services/api/client';
import { notificationService } from '@/services/notifications';

type Status = 'idle' | 'loading' | 'ready' | 'error';

interface CrossRunEntry {
  data: unknown | null;
  status: Status;
  error: string;
  computedAt: string;
  isStale: boolean;
  newRunsSince: number;
  sourceRunCount: number;
}

interface CrossRunState {
  entries: Partial<Record<AppId, CrossRunEntry>>;
  loadAnalytics: (appId: AppId) => Promise<void>;
  refreshAnalytics: (appId: AppId, limit?: number) => Promise<void>;
  clear: (appId: AppId) => void;
  reset: () => void;
}

const createInitialEntry = (): CrossRunEntry => ({
  data: null,
  status: 'idle',
  error: '',
  computedAt: '',
  isStale: false,
  newRunsSince: 0,
  sourceRunCount: 0,
});

const getEntry = (
  entries: Partial<Record<AppId, CrossRunEntry>>,
  appId: AppId,
): CrossRunEntry => entries[appId] ?? createInitialEntry();

export const useCrossRunStore = create<CrossRunState>()(
  persist(
    (set, get) => ({
      entries: {},

      loadAnalytics: async (appId: AppId) => {
        const current = getEntry(get().entries, appId);
        if (current.status === 'loading') return;

        set((state) => ({
          entries: {
            ...state.entries,
            [appId]: {
              ...getEntry(state.entries, appId),
              status: 'loading',
              error: '',
            },
          },
        }));

        try {
          const result = await reportsApi.fetchCrossRunAnalytics(appId);
          set((state) => ({
            entries: {
              ...state.entries,
              [appId]: {
                data: result.analytics,
                status: 'ready',
                error: '',
                computedAt: result.computedAt,
                isStale: result.isStale,
                newRunsSince: result.newRunsSince,
                sourceRunCount: result.sourceRunCount,
              },
            },
          }));
        } catch (e: unknown) {
          if (e instanceof ApiError && e.status === 404) {
            set((state) => ({
              entries: {
                ...state.entries,
                [appId]: createInitialEntry(),
              },
            }));
            return;
          }
          const msg = e instanceof Error ? e.message : 'Failed to load analytics';
          set((state) => ({
            entries: {
              ...state.entries,
              [appId]: {
                ...getEntry(state.entries, appId),
                status: 'error',
                error: msg,
              },
            },
          }));
          notificationService.error(msg);
        }
      },

      refreshAnalytics: async (appId: AppId, limit?: number) => {
        const current = getEntry(get().entries, appId);
        if (current.status === 'loading') return;

        set((state) => ({
          entries: {
            ...state.entries,
            [appId]: {
              ...getEntry(state.entries, appId),
              status: 'loading',
              error: '',
            },
          },
        }));

        try {
          const result = await reportsApi.refreshCrossRunAnalytics(appId, limit || 50);
          set((state) => ({
            entries: {
              ...state.entries,
              [appId]: {
                data: result.analytics,
                status: 'ready',
                error: '',
                computedAt: result.computedAt,
                isStale: false,
                newRunsSince: 0,
                sourceRunCount: result.sourceRunCount,
              },
            },
          }));
        } catch (e: unknown) {
          if (e instanceof ApiError && e.status === 404) {
            set((state) => ({
              entries: {
                ...state.entries,
                [appId]: createInitialEntry(),
              },
            }));
            notificationService.info('No runs with generated reports found. Generate a report first.');
            return;
          }
          const msg = e instanceof Error ? e.message : 'Failed to refresh analytics';
          set((state) => ({
            entries: {
              ...state.entries,
              [appId]: {
                ...getEntry(state.entries, appId),
                status: 'error',
                error: msg,
              },
            },
          }));
          notificationService.error(msg);
        }
      },

      clear: (appId: AppId) =>
        set((state) => ({
          entries: {
            ...state.entries,
            [appId]: createInitialEntry(),
          },
        })),

      reset: () => set({ entries: {} }),
    }),
    {
      name: 'cross-run-analytics',
      storage: {
        getItem: (name) => {
          const value = sessionStorage.getItem(name);
          return value ? JSON.parse(value) : null;
        },
        setItem: (name, value) => sessionStorage.setItem(name, JSON.stringify(value)),
        removeItem: (name) => sessionStorage.removeItem(name),
      },
      partialize: (state) => ({
        entries: Object.fromEntries(
          Object.entries(state.entries).map(([appId, entry]) => [
            appId,
            {
              ...entry,
              status: entry?.data ? 'ready' : 'idle',
              error: '',
            },
          ]),
        ) as Partial<Record<AppId, CrossRunEntry>>,
      }) as unknown as CrossRunState,
    }
  )
);
