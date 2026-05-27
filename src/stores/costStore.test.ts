import { describe, expect, it, vi, beforeEach } from 'vitest';

import { useCostStore } from './costStore';
import type { ModalityBreakdown, CostSignalsSnapshot, CostOverview } from '@/features/cost/types';

// Mock the entire costApi so no real HTTP calls are made.
vi.mock('@/services/api/costApi', () => ({
  costApi: {
    fetchModality: vi.fn(),
    fetchSignals: vi.fn(),
    fetchOverview: vi.fn(),
    fetchSpend: vi.fn(),
    fetchEfficiency: vi.fn(),
    fetchEntities: vi.fn(),
    fetchCalls: vi.fn(),
    fetchPricingBundle: vi.fn(),
    fetchEntity: vi.fn(),
    fetchCall: vi.fn(),
    batchChips: vi.fn(),
    createPricing: vi.fn(),
    patchPricing: vi.fn(),
    refreshPricing: vi.fn(),
    backfillUnpriced: vi.fn(),
    fetchSnapshot: vi.fn(),
    backfillRollup: vi.fn(),
    fetchAliases: vi.fn(),
    fetchUnmappedModels: vi.fn(),
    upsertAlias: vi.fn(),
    deleteAlias: vi.fn(),
    repriceAlias: vi.fn(),
  },
}));

// Also silence notificationService so error paths don't throw.
vi.mock('@/services/notifications', () => ({
  notificationService: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

// Re-import the mocked module so we can configure return values per test.
import { costApi } from '@/services/api/costApi';

const MODALITY_FIXTURE: ModalityBreakdown = {
  modalities: [{ modality: 'text', tokens: 1000, costUsd: 0.5, estimated: false }],
  totalTokens: 1000,
  totalCostUsd: 0.5,
  computedAt: '2026-05-27T00:00:00Z',
};

const SIGNALS_FIXTURE: CostSignalsSnapshot = {
  signals: [{ severity: 'info', title: 'All good', detail: 'No issues detected', metric: null }],
  generatedAt: '2026-05-27T00:00:00Z',
  model: 'gemini',
  period: '7d',
};

const OVERVIEW_FIXTURE: CostOverview = {
  kpis: {
    totalCostUsd: 10,
    totalTokens: 5000,
    totalCalls: 20,
    errorCalls: 0,
    pricingFallbackCalls: 0,
  },
  timeSeries: [],
  spendByApp: [],
  spendByPurpose: [],
  signals: {},
  computedAt: '2026-05-27T00:00:00Z',
};

function resetStore() {
  useCostStore.getState().reset();
  vi.clearAllMocks();
}

describe('costStore — modality slice', () => {
  beforeEach(resetStore);

  it('loadModality sets slice to ready with fetched data', async () => {
    vi.mocked(costApi.fetchModality).mockResolvedValue(MODALITY_FIXTURE);

    await useCostStore.getState().loadModality();

    const { modality } = useCostStore.getState();
    expect(modality.status).toBe('ready');
    expect(modality.data).toEqual(MODALITY_FIXTURE);
    expect(costApi.fetchModality).toHaveBeenCalledOnce();
  });

  it('loadModality does NOT re-fetch when already ready with the same filtersKey', async () => {
    vi.mocked(costApi.fetchModality).mockResolvedValue(MODALITY_FIXTURE);

    await useCostStore.getState().loadModality();
    await useCostStore.getState().loadModality();

    // Second call should be skipped because status=ready and filtersKey matches.
    expect(costApi.fetchModality).toHaveBeenCalledOnce();
  });

  it('loadModality re-fetches after setFilters resets the slice', async () => {
    vi.mocked(costApi.fetchModality).mockResolvedValue(MODALITY_FIXTURE);

    await useCostStore.getState().loadModality();
    expect(costApi.fetchModality).toHaveBeenCalledOnce();

    // Change filters — this resets all slices to idle.
    useCostStore.getState().setFilters({ range: '24h' });
    expect(useCostStore.getState().modality.status).toBe('idle');

    await useCostStore.getState().loadModality();
    expect(costApi.fetchModality).toHaveBeenCalledTimes(2);
  });
});

describe('costStore — signals slice', () => {
  beforeEach(resetStore);

  it('loadSignals sets slice to ready with fetched data', async () => {
    vi.mocked(costApi.fetchSignals).mockResolvedValue(SIGNALS_FIXTURE);

    await useCostStore.getState().loadSignals();

    const { signals } = useCostStore.getState();
    expect(signals.status).toBe('ready');
    expect(signals.data).toEqual(SIGNALS_FIXTURE);
  });

  it('loadSignals is load-once: a second call while ready does not re-fetch', async () => {
    vi.mocked(costApi.fetchSignals).mockResolvedValue(SIGNALS_FIXTURE);

    await useCostStore.getState().loadSignals();
    await useCostStore.getState().loadSignals();

    expect(costApi.fetchSignals).toHaveBeenCalledOnce();
  });
});

describe('costStore — refreshActive("overview")', () => {
  beforeEach(resetStore);

  it('resets and reloads both overview and signals slices', async () => {
    vi.mocked(costApi.fetchOverview).mockResolvedValue(OVERVIEW_FIXTURE);
    vi.mocked(costApi.fetchSignals).mockResolvedValue(SIGNALS_FIXTURE);

    // Prime the signals slice so it is already ready before the refresh.
    await useCostStore.getState().loadSignals();
    expect(useCostStore.getState().signals.status).toBe('ready');
    expect(costApi.fetchSignals).toHaveBeenCalledOnce();

    // Also prime overview.
    await useCostStore.getState().loadOverview();
    expect(useCostStore.getState().overview.status).toBe('ready');

    vi.clearAllMocks();

    // refreshActive('overview') must reset both slices and re-fetch.
    vi.mocked(costApi.fetchOverview).mockResolvedValue(OVERVIEW_FIXTURE);
    vi.mocked(costApi.fetchSignals).mockResolvedValue(SIGNALS_FIXTURE);

    await useCostStore.getState().refreshActive('overview');

    expect(useCostStore.getState().overview.status).toBe('ready');
    expect(useCostStore.getState().signals.status).toBe('ready');

    // fetchSignals MUST be called again even though the slice was already ready.
    expect(costApi.fetchSignals).toHaveBeenCalledOnce();
    expect(costApi.fetchOverview).toHaveBeenCalledOnce();
  });
});
