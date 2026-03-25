import { create } from 'zustand';
import { apiRequest } from '@/services/api/client';
import { fetchLeads as apiFetchLeads } from '@/services/api/insideSales';
import type { LeadListRecord, LeadFilters } from '@/services/api/insideSales';

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
  lastEvalScore?: number;
  evalCount?: number;
}

export interface CallFilters {
  dateFrom: string;
  dateTo: string;
  agents: string[];
  prospectId: string;
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
  /** Cache key for the last successful fetch — skip re-fetch if unchanged */
  _lastFetchKey: string;
  /** Currently viewed call (set when clicking into detail) */
  activeCall: CallRecord | null;
  setActiveCall: (call: CallRecord | null) => void;

  setFilters: (filters: Partial<CallFilters>) => void;
  clearFilters: () => void;
  setPage: (page: number) => void;
  toggleCallSelection: (activityId: string) => void;
  selectAllOnPage: () => void;
  deselectAll: () => void;
  loadCalls: (force?: boolean) => Promise<void>;
  reset: () => void;
}

function todayDateString(): string {
  return new Date().toISOString().split('T')[0];
}

const DEFAULT_FILTERS: CallFilters = {
  dateFrom: todayDateString() + ' 00:00:00',
  dateTo: todayDateString() + ' 23:59:59',
  agents: [],
  prospectId: '',
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
  _lastFetchKey: '',
  activeCall: null,

  setActiveCall: (call) => set({ activeCall: call }),

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

  loadCalls: async (force?: boolean) => {
    const { filters, page, pageSize, _lastFetchKey } = get();
    const fetchKey = `${filters.dateFrom}|${filters.dateTo}|${filters.agents.join(',')}|${filters.prospectId}|${filters.direction}|${filters.status}|${filters.eventCodes}|${page}|${pageSize}`;

    // Skip if already loaded for this exact filter+page combo
    if (!force && fetchKey === _lastFetchKey) return;

    set({ isLoading: true, error: null });
    try {
      const params = new URLSearchParams({
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
        page: String(page),
        page_size: String(pageSize),
      });
      if (filters.agents.length > 0) params.set('agents', filters.agents.join(','));
      if (filters.prospectId) params.set('prospect_id', filters.prospectId);
      if (filters.direction) params.set('direction', filters.direction);
      if (filters.status) params.set('status', filters.status);
      if (filters.eventCodes) params.set('event_codes', filters.eventCodes);

      const data = await apiRequest<{
        calls: CallRecord[];
        total: number;
        page: number;
        pageSize: number;
      }>(`/api/inside-sales/calls?${params.toString()}`);

      set({ calls: data.calls, total: data.total, isLoading: false, _lastFetchKey: fetchKey });
    } catch (e) {
      const msg = e instanceof Error ? e.message : typeof e === 'string' ? e : 'Failed to load calls';
      set({
        error: msg,
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
      _lastFetchKey: '',
      activeCall: null,
    }),
}));

// Re-export types so pages can import from one place
export type { LeadListRecord, LeadFilters };

const DEFAULT_LEAD_FILTERS: LeadFilters = {
  dateFrom: todayDateString() + ' 00:00:00',
  dateTo: todayDateString() + ' 23:59:59',
  agents: [],
  stage: [],
  mqlMin: '',
  condition: [],
  city: '',
};

interface LeadsState {
  leads: LeadListRecord[];
  leadsTotal: number;
  leadsPage: number;
  leadsPageSize: number;
  leadsLoading: boolean;
  leadsError: string | null;
  leadFilters: LeadFilters;

  setLeadFilters: (updates: Partial<LeadFilters>) => void;
  clearLeadFilters: () => void;
  setLeadsPage: (page: number) => void;
  loadLeads: () => Promise<void>;
}

export const useLeadsStore = create<LeadsState>((set, get) => ({
  leads: [],
  leadsTotal: 0,
  leadsPage: 1,
  leadsPageSize: 50,
  leadsLoading: false,
  leadsError: null,
  leadFilters: { ...DEFAULT_LEAD_FILTERS },

  setLeadFilters: (updates) =>
    set((s) => ({ leadFilters: { ...s.leadFilters, ...updates }, leadsPage: 1 })),

  clearLeadFilters: () =>
    set({ leadFilters: { ...DEFAULT_LEAD_FILTERS }, leadsPage: 1 }),

  setLeadsPage: (page) => set({ leadsPage: page }),

  loadLeads: async () => {
    const { leadFilters, leadsPage, leadsPageSize } = get();
    set({ leadsLoading: true, leadsError: null });
    try {
      const data = await apiFetchLeads(leadFilters, leadsPage, leadsPageSize);
      set({ leads: data.leads, leadsTotal: data.total, leadsLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load leads';
      set({ leadsError: msg, leadsLoading: false });
    }
  },
}));
