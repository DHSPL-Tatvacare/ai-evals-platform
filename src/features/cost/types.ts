/**
 * Cost & usage dashboard — TypeScript mirror of backend response shapes.
 *
 * Source of truth: `backend/app/routes/cost.py`. Keep field names in sync
 * with the `CamelModel` payloads.
 */

export type RangeToken = '24h' | '7d' | '30d' | 'mtd' | string;

export interface CostFilters {
  range: RangeToken;
  appId?: string;
  provider?: string;
  model?: string;
}

export interface CostKpi {
  totalCostUsd: number;
  totalTokens: number;
  totalCalls: number;
  errorCalls: number;
  pricingFallbackCalls: number;
}

export interface TimeSeriesPoint {
  day: string;
  costUsd: number;
  tokens: number;
  calls: number;
}

export interface GroupedSpend {
  key: string;
  costUsd: number;
  tokens: number;
  calls: number;
}

export interface CostOverview {
  kpis: CostKpi;
  timeSeries: TimeSeriesPoint[];
  spendByApp: GroupedSpend[];
  spendByPurpose: GroupedSpend[];
  signals: Record<string, unknown>;
  computedAt: string;
}

export interface SpendBundle {
  byApp: GroupedSpend[];
  byPurpose: GroupedSpend[];
  topModels: GroupedSpend[];
  topUsers: GroupedSpend[];
  computedAt: string;
}

export interface EfficiencyGaugePoint {
  label: string;
  value: number;
}

export interface EfficiencyBundle {
  cacheGauge: EfficiencyGaugePoint[];
  cacheByPurpose: GroupedSpend[];
  errorGauge: EfficiencyGaugePoint[];
  errorByCode: GroupedSpend[];
  unpricedCalls: GroupedSpend[];
  reasoningByModel: GroupedSpend[];
  computedAt: string;
}

export type OwnerType =
  | 'eval_run'
  | 'sherlock_turn'
  | 'report_run'
  | 'job'
  | 'standalone'
  | (string & {});

export interface EntityRow {
  ownerType: OwnerType;
  ownerId: string | null;
  /** Human-readable label resolved server-side — listing title for eval_run,
   * truncated user_message for sherlock_turn, job_type for job, etc.
   * ``null`` when the owner source row has been deleted. */
  displayName: string | null;
  /** Representative app for the workload; ``null`` when it spans multiple apps. */
  appId: string | null;
  costUsd: number;
  totalTokens: number;
  callCount: number;
  firstAt: string | null;
  lastAt: string | null;
}

export interface EntityListPage {
  items: EntityRow[];
  total: number;
  page: number;
  pageSize: number;
}

export interface EntityCostBreakdown {
  ownerType: OwnerType;
  ownerId: string | null;
  costUsd: number;
  totalTokens: number;
  callCount: number;
  byPurpose: GroupedSpend[];
  byModel: GroupedSpend[];
}

export interface ChipSummary {
  costUsd: number;
  totalTokens: number;
  callCount: number;
}

export interface BatchLookupItem {
  ownerType: OwnerType;
  ownerId: string;
}

export interface CallRow {
  id: string;
  createdAt: string;
  tenantId: string;
  userId: string | null;
  appId: string;
  subsystem: string | null;
  ownerType: OwnerType;
  ownerId: string | null;
  provider: string;
  model: string;
  callPurpose: string | null;
  status: string;
  inputTokens: number;
  outputTokens: number;
  cachedReadTokens: number;
  reasoningTokens: number;
  totalTokens: number;
  costUsd: number;
  pricingFallback: boolean;
  durationMs: number | null;
  correlationId: string | null;
}

export interface CallDetail extends CallRow {
  costBreakdown: Record<string, unknown> | null;
  modalityDetails: Record<string, unknown> | null;
  serverToolUsage: Record<string, unknown> | null;
  finishReason: string | null;
  requestId: string | null;
  errorCode: string | null;
  trafficType: string | null;
}

export interface CallsPage {
  items: CallRow[];
  total: number;
  page: number;
  pageSize: number;
}

export interface PricingRow {
  id: string;
  provider: string;
  model: string;
  effectiveFrom: string;
  effectiveTo: string | null;
  inputPer1MUsd: number;
  outputPer1MUsd: number;
  cachedReadPer1MUsd: number;
  cacheWrite5MPer1MUsd: number;
  cacheWrite1HPer1MUsd: number;
  reasoningPer1MUsd: number;
  audioInputPer1MUsd: number | null;
  audioInputPerMinuteUsd: number | null;
  imageInputPer1MUsd: number | null;
  serverToolPrices: Record<string, unknown> | null;
  currency: string;
  source: string;
  sourceSnapshotId: string | null;
  sourceModelId: string | null;
  notes: string | null;
  createdAt: string;
  createdBy: string | null;
}

export interface CatalogRow {
  provider: string;
  model: string;
  displayName: string | null;
  family: string | null;
  contextLimit: number | null;
  outputLimit: number | null;
  supportsReasoning: boolean;
  supportsToolCall: boolean;
  modalitiesInput: string[];
  modalitiesOutput: string[];
  status: string;
  lastSeenAt: string;
}

export interface SnapshotRow {
  id: string;
  fetchedAt: string;
  status: string;
  addedCount: number;
  updatedCount: number;
  unchangedCount: number;
  removedCount: number;
  payloadHash: string;
  errorMessage: string | null;
  durationMs: number | null;
}

export interface PricingBundle {
  pricing: PricingRow[];
  catalog: CatalogRow[];
  refreshHistory: SnapshotRow[];
}

export interface PricingCreatePayload {
  provider: string;
  model: string;
  inputPer1MUsd?: number;
  outputPer1MUsd?: number;
  cachedReadPer1MUsd?: number;
  cacheWrite5MPer1MUsd?: number;
  cacheWrite1HPer1MUsd?: number;
  reasoningPer1MUsd?: number;
  audioInputPer1MUsd?: number | null;
  audioInputPerMinuteUsd?: number | null;
  imageInputPer1MUsd?: number | null;
  serverToolPrices?: Record<string, unknown> | null;
  currency?: string;
  notes?: string | null;
}

export type PricingPatchPayload = Partial<Omit<PricingCreatePayload, 'provider' | 'model' | 'currency'>>;

export interface RefreshDiff {
  snapshotId: string;
  status: string;
  addedCount: number;
  updatedCount: number;
  unchangedCount: number;
  removedCount: number;
  modelCount: number;
  payloadHash: string;
  deduped: boolean;
}

export interface BackfillResponse {
  daysProcessed: number;
  rowsUpserted: number;
  tenants: string[];
}

export interface UnpricedBackfillResponse {
  scanned: number;
  repriced: number;
  stillUnpriced: number;
  daysRolled: number;
}

export interface AliasRow {
  id: string;
  tenantId: string | null;
  provider: string;
  observed: string;
  canonical: string;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
  createdBy: string | null;
}

export interface UnmappedModelRow {
  provider: string;
  model: string;
  callCount: number;
  lastSeenAt: string;
  tenantId: string;
  suggestedCanonical: string | null;
}

export interface AliasUpsertPayload {
  provider: string;
  observed: string;
  canonical: string;
  tenantScope?: 'tenant' | 'system';
  notes?: string | null;
}

export interface AliasRepriceResponse {
  scanned: number;
  repriced: number;
  stillUnpriced: number;
  daysRolled: number;
}
