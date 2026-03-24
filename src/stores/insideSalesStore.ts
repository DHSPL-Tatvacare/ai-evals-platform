import { create } from 'zustand';
import { apiRequest } from '@/services/api/client';

export interface CallRecord {
  activityId: string;
  prospectId: string;
  agentName: string;
  agentEmail: string;
  eventCode: number;
  direction: 'inbound' | 'outbound';
  status: string;
  callStartTime: string;
  durationSeconds: number;
  recordingUrl: string;
  phoneNumber: string;
  displayNumber: string;
  callNotes: string;
  callSessionId: string;
  createdOn: string;
  leadName: string;
}

export interface CallFilters {
  dateFrom: string;
  dateTo: string;
  agent: string;
  direction: string;
  status: string;
  eventCodes: string;
  evalStatus: string;
  durationMin: string;
  durationMax: string;
  scoreMin: string;
  scoreMax: string;
  search: string;
}

interface InsideSalesState {
  calls: CallRecord[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  error: string | null;
  filters: CallFilters;
  selectedCallIds: Set<string>;

  setFilters: (filters: Partial<CallFilters>) => void;
  clearFilters: () => void;
  setPage: (page: number) => void;
  toggleCallSelection: (activityId: string) => void;
  selectAllOnPage: () => void;
  deselectAll: () => void;
  loadCalls: () => Promise<void>;
  reset: () => void;
}

function todayDateString(): string {
  return new Date().toISOString().split('T')[0];
}

const DEFAULT_FILTERS: CallFilters = {
  dateFrom: todayDateString() + ' 00:00:00',
  dateTo: todayDateString() + ' 23:59:59',
  agent: '',
  direction: '',
  status: '',
  eventCodes: '',
  evalStatus: '',
  durationMin: '',
  durationMax: '',
  scoreMin: '',
  scoreMax: '',
  search: '',
};

export const useInsideSalesStore = create<InsideSalesState>((set, get) => ({
  calls: [],
  total: 0,
  page: 1,
  pageSize: 50,
  isLoading: false,
  error: null,
  filters: { ...DEFAULT_FILTERS },
  selectedCallIds: new Set(),

  setFilters: (updates) =>
    set((s) => ({ filters: { ...s.filters, ...updates }, page: 1 })),

  clearFilters: () => set({ filters: { ...DEFAULT_FILTERS }, page: 1 }),

  setPage: (page) => set({ page }),

  toggleCallSelection: (activityId) =>
    set((s) => {
      const next = new Set(s.selectedCallIds);
      if (next.has(activityId)) next.delete(activityId);
      else next.add(activityId);
      return { selectedCallIds: next };
    }),

  selectAllOnPage: () =>
    set((s) => ({
      selectedCallIds: new Set(s.calls.map((c) => c.activityId)),
    })),

  deselectAll: () => set({ selectedCallIds: new Set() }),

  loadCalls: async () => {
    const { filters, page, pageSize } = get();
    set({ isLoading: true, error: null });
    try {
      const params = new URLSearchParams({
        dateFrom: filters.dateFrom,
        dateTo: filters.dateTo,
        page: String(page),
        pageSize: String(pageSize),
      });
      if (filters.agent) params.set('agent', filters.agent);
      if (filters.direction) params.set('direction', filters.direction);
      if (filters.status) params.set('status', filters.status);
      if (filters.eventCodes) params.set('eventCodes', filters.eventCodes);

      const data = await apiRequest<{
        calls: CallRecord[];
        total: number;
        page: number;
        pageSize: number;
      }>(`/api/inside-sales/calls?${params.toString()}`);

      set({ calls: data.calls, total: data.total, isLoading: false });
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : 'Failed to load calls',
        isLoading: false,
      });
    }
  },

  reset: () =>
    set({
      calls: [],
      total: 0,
      page: 1,
      isLoading: false,
      error: null,
      filters: { ...DEFAULT_FILTERS },
      selectedCallIds: new Set(),
    }),
}));
