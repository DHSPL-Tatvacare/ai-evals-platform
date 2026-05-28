/**
 * Orchestration analytics response types. Mirror the backend CamelModels in
 * `backend/app/schemas/orchestration_analytics.py` exactly — JSON is camelCase.
 */

export type AnalyticsScope = 'mine' | 'tenant';
export type BreakdownDimension = 'campaign' | 'channel' | 'connection';

export interface OrchestrationOverview {
  campaigns: number;
  runs: number;
  recipients: number;
  uniqueContacts: number;
  positive: number;
  reached: number;
  noResponse: number;
  failed: number;
  inFlight: number;
  spend: number;
  inFlightRuns: number;
}

export interface OrchestrationBreakdownRow {
  key: string;
  label: string;
  provider?: string | null;
  recipients: number;
  dispatched: number;
  positive: number;
  reached: number;
  noResponse: number;
  failed: number;
  inFlight: number;
  avgCost: number;
  cost: number;
}

export interface OrchestrationBreakdown {
  dimension: string;
  rows: OrchestrationBreakdownRow[];
}

export interface OrchestrationRunRow {
  runId: string;
  workflowId: string;
  workflowName: string;
  channel?: string | null;
  triggeredBy: string;
  status: string;
  cohortSize: number;
  reached: number;
  positive: number;
  cost: number;
  startedAt?: string | null;
}

export interface OrchestrationRuns {
  rows: OrchestrationRunRow[];
  total: number;
  page: number;
  pageSize: number;
}

export interface OrchestrationRunBuckets {
  positive: number;
  reached: number;
  noResponse: number;
  failed: number;
  inFlight: number;
}

export interface OrchestrationRunNodeStep {
  nodeStepId: string;
  nodeId: string;
  nodeType: string;
  status: string;
  startedAt?: string | null;
  completedAt?: string | null;
}

export interface OrchestrationRunAction {
  actionId: string;
  recipientId: string;
  channel: string;
  actionType: string;
  status: string;
  outcomeBucket?: string | null;
  contact?: string | null;
  cost?: number | null;
  createdAt?: string | null;
}

export interface OrchestrationRunDetail {
  runId: string;
  workflowId: string;
  workflowName: string;
  status: string;
  triggeredBy: string;
  cohortSize: number;
  startedAt?: string | null;
  completedAt?: string | null;
  buckets: OrchestrationRunBuckets;
  spend: number;
  nodeSteps: OrchestrationRunNodeStep[];
  actions: OrchestrationRunAction[];
  actionsTotal: number;
}

export interface OrchestrationSignal {
  severity: string;
  title: string;
  detail: string;
  metric?: Record<string, unknown> | null;
}

export interface OrchestrationSignals {
  signals: OrchestrationSignal[];
  generatedAt?: string | null;
}

/** Shared range + scope inputs for every analytics query. */
export interface AnalyticsQueryParams {
  appId: string;
  scope: AnalyticsScope;
  from?: string | null;
  to?: string | null;
}
