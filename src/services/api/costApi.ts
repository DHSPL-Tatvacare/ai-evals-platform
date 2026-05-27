import { apiRequest } from './client';
import type {
  AliasRepriceResponse,
  AliasRow,
  AliasUpsertPayload,
  BackfillResponse,
  BatchLookupItem,
  CallDetail,
  CallsPage,
  ChipSummary,
  CostFilters,
  CostOverview,
  EfficiencyBundle,
  EntityCostBreakdown,
  EntityListPage,
  ModalityBreakdown,
  OwnerType,
  PricingBundle,
  PricingCreatePayload,
  PricingPatchPayload,
  PricingRow,
  RefreshDiff,
  SnapshotRow,
  SpendBundle,
  UnmappedModelRow,
  UnpricedBackfillResponse,
} from '@/features/cost/types';

function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join('&')}` : '';
}

function applyFiltersQuery(
  filters: Pick<CostFilters, 'range' | 'appId' | 'provider' | 'model'>,
  extra: Record<string, string | number | undefined | null> = {},
): string {
  return buildQuery({
    range: filters.range,
    app_id: filters.appId,
    provider: filters.provider,
    model: filters.model,
    ...extra,
  });
}

export const costApi = {
  fetchOverview: (filters: CostFilters): Promise<CostOverview> =>
    apiRequest<CostOverview>(`/api/cost/overview${applyFiltersQuery(filters)}`),

  fetchSpend: (filters: CostFilters): Promise<SpendBundle> =>
    apiRequest<SpendBundle>(`/api/cost/spend${applyFiltersQuery(filters)}`),

  fetchModality: (filters: CostFilters): Promise<ModalityBreakdown> =>
    apiRequest<ModalityBreakdown>(`/api/cost/modality${applyFiltersQuery(filters)}`),

  fetchEfficiency: (filters: CostFilters): Promise<EfficiencyBundle> =>
    apiRequest<EfficiencyBundle>(`/api/cost/efficiency${applyFiltersQuery(filters)}`),

  fetchEntities: (
    filters: CostFilters,
    page: number,
    pageSize = 25,
    sort: 'cost_desc' | 'calls_desc' | 'recent' = 'cost_desc',
    ownerType?: string,
    q?: string,
  ): Promise<EntityListPage> =>
    apiRequest<EntityListPage>(
      `/api/cost/entities${applyFiltersQuery(filters, {
        page,
        page_size: pageSize,
        sort,
        owner_type: ownerType,
        q,
      })}`,
    ),

  fetchEntity: (
    ownerType: OwnerType,
    ownerId: string,
    filters: Pick<CostFilters, 'range' | 'appId' | 'provider' | 'model'>,
  ): Promise<EntityCostBreakdown> =>
    apiRequest<EntityCostBreakdown>(
      `/api/cost/entity/${encodeURIComponent(ownerType)}/${encodeURIComponent(ownerId)}${applyFiltersQuery(filters)}`,
    ),

  batchChips: (
    filters: Pick<CostFilters, 'range' | 'appId' | 'provider' | 'model'>,
    items: BatchLookupItem[],
  ): Promise<Record<string, ChipSummary>> =>
    apiRequest<Record<string, ChipSummary>>(`/api/cost/entity/batch`, {
      method: 'POST',
      body: JSON.stringify({
        range: filters.range,
        appId: filters.appId,
        provider: filters.provider,
        model: filters.model,
        items: items.map((it) => ({ ownerType: it.ownerType, ownerId: it.ownerId })),
      }),
    }),

  fetchCalls: (
    filters: CostFilters,
    page: number,
    pageSize = 50,
    opts: { ownerType?: string; status?: string; q?: string } = {},
  ): Promise<CallsPage> =>
    apiRequest<CallsPage>(
      `/api/cost/calls${applyFiltersQuery(filters, {
        page,
        page_size: pageSize,
        owner_type: opts.ownerType,
        status: opts.status,
        q: opts.q,
      })}`,
    ),

  fetchCall: (callId: string): Promise<CallDetail> =>
    apiRequest<CallDetail>(`/api/cost/calls/${encodeURIComponent(callId)}`),

  fetchPricingBundle: (activeOnly = true): Promise<PricingBundle> =>
    apiRequest<PricingBundle>(`/api/cost/pricing/bundle${buildQuery({ active_only: activeOnly ? 'true' : 'false' })}`),

  createPricing: (payload: PricingCreatePayload): Promise<PricingRow> =>
    apiRequest<PricingRow>(`/api/cost/pricing`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  patchPricing: (pricingId: string, payload: PricingPatchPayload): Promise<PricingRow> =>
    apiRequest<PricingRow>(`/api/cost/pricing/${encodeURIComponent(pricingId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  refreshPricing: (): Promise<RefreshDiff> =>
    apiRequest<RefreshDiff>(`/api/cost/pricing/refresh`, { method: 'POST' }),

  backfillUnpriced: (opts: { allTenants?: boolean; limit?: number } = {}): Promise<UnpricedBackfillResponse> =>
    apiRequest<UnpricedBackfillResponse>(`/api/cost/pricing/backfill-unpriced`, {
      method: 'POST',
      body: JSON.stringify({
        all_tenants: opts.allTenants ?? false,
        limit: opts.limit ?? null,
      }),
    }),

  fetchSnapshot: (snapshotId: string): Promise<SnapshotRow> =>
    apiRequest<SnapshotRow>(`/api/cost/pricing/refresh/${encodeURIComponent(snapshotId)}`),

  backfillRollup: (start: string, end: string): Promise<BackfillResponse> =>
    apiRequest<BackfillResponse>(`/api/admin/cost-rollup/backfill`, {
      method: 'POST',
      body: JSON.stringify({ start, end }),
    }),

  fetchAliases: (provider?: string): Promise<{ aliases: AliasRow[] }> =>
    apiRequest<{ aliases: AliasRow[] }>(`/api/cost/aliases${buildQuery({ provider })}`),

  fetchUnmappedModels: (): Promise<{ rows: UnmappedModelRow[] }> =>
    apiRequest<{ rows: UnmappedModelRow[] }>(`/api/cost/aliases/unmapped`),

  upsertAlias: (payload: AliasUpsertPayload): Promise<AliasRow> =>
    apiRequest<AliasRow>(`/api/cost/aliases`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteAlias: (aliasId: string): Promise<{ ok: boolean }> =>
    apiRequest<{ ok: boolean }>(`/api/cost/aliases/${encodeURIComponent(aliasId)}`, {
      method: 'DELETE',
    }),

  repriceAlias: (aliasId: string): Promise<AliasRepriceResponse> =>
    apiRequest<AliasRepriceResponse>(
      `/api/cost/aliases/${encodeURIComponent(aliasId)}/reprice`,
      { method: 'POST' },
    ),
};
