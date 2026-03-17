import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { CrossRunAnalytics } from '@/types/crossRunAnalytics';
import { reportsApi } from '@/services/api/reportsApi';
import { ApiError } from '@/services/api/client';
import { notificationService } from '@/services/notifications';

type Status = 'idle' | 'loading' | 'ready' | 'error';

interface CrossRunState {
  data: CrossRunAnalytics | null;
  status: Status;
  error: string;
  computedAt: string;
  isStale: boolean;
  newRunsSince: number;
  sourceRunCount: number;

  loadAnalytics: () => Promise<void>;
  refreshAnalytics: (limit?: number) => Promise<void>;
  clear: () => void;
  reset: () => void;
}

const INITIAL = {
  data: null,
  status: 'idle' as Status,
  error: '',
  computedAt: '',
  isStale: false,
  newRunsSince: 0,
  sourceRunCount: 0,
};

export const useCrossRunStore = create<CrossRunState>()(
  persist(
    (set, get) => ({
      ...INITIAL,

      loadAnalytics: async () => {
        if (get().status === 'loading') return;
        set({ status: 'loading', error: '' });
        try {
          const result = await reportsApi.fetchCrossRunAnalytics('kaira-bot');
          set({
            data: result.analytics,
            status: 'ready',
            computedAt: result.computedAt,
            isStale: result.isStale,
            newRunsSince: result.newRunsSince,
            sourceRunCount: result.sourceRunCount,
          });
        } catch (e: unknown) {
          // 404 = no cache yet (or no runs with reports) → idle, not error
          if (e instanceof ApiError && e.status === 404) {
            set({ ...INITIAL });
            return;
          }
          const msg = e instanceof Error ? e.message : 'Failed to load analytics';
          set({ error: msg, status: 'error' });
          notificationService.error(msg);
        }
      },

      refreshAnalytics: async (limit?: number) => {
        if (get().status === 'loading') return;
        set({ status: 'loading', error: '' });
        try {
          const result = await reportsApi.refreshCrossRunAnalytics('kaira-bot', limit || 50);
          set({
            data: result.analytics,
            status: 'ready',
            computedAt: result.computedAt,
            isStale: false,
            newRunsSince: 0,
            sourceRunCount: result.sourceRunCount,
          });
        } catch (e: unknown) {
          // 404 = no runs with generated reports yet → idle with friendly message
          if (e instanceof ApiError && e.status === 404) {
            set({ ...INITIAL });
            notificationService.info('No runs with generated reports found. Generate a report first.');
            return;
          }
          const msg = e instanceof Error ? e.message : 'Failed to refresh analytics';
          set({ error: msg, status: 'error' });
          notificationService.error(msg);
        }
      },

      clear: () => set({ ...INITIAL }),
      reset: () => set({ ...INITIAL }),
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
        data: state.data,
        status: (state.data ? 'ready' : 'idle') as Status,
        computedAt: state.computedAt,
        isStale: state.isStale,
        newRunsSince: state.newRunsSince,
        sourceRunCount: state.sourceRunCount,
      } as unknown as CrossRunState),
    }
  )
);
