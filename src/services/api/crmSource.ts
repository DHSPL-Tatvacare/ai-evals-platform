import { apiRequest } from './client';

/** CRM ingestion API — discovery, grain schema, field maps, sync/unpack, sync activity.
 *  Mirrors the backend `/api/crm` router (camelCase JSON). The connection itself is
 *  managed through `orchestrationConnections`; this surface owns mapping + ingestion. */

export interface DiscoveredObject {
  sourceObject: string;
  recordType: string;
  fields: string[];
}

export interface CrmStandardColumn {
  target: string;
  label: string;
  dataType: string;
}

export interface CrmGrainSchema {
  recordType: string;
  naturalKeyTarget: string;
  leadLinkTarget: string;
  leadLinkRequired: boolean;
  expectedTargets: string[];
  standardColumns: CrmStandardColumn[];
  slots: Record<string, string[]>;
}

export interface CrmFieldBinding {
  slot: string;
  semanticKey: string;
  sourceField: string;
  dataType: string;
  valueMap: Record<string, string> | null;
  description?: string | null;
  version?: number;
}

export interface CrmFieldMap {
  recordType: string;
  version: number;
  bindings: CrmFieldBinding[];
}

export interface CrmFieldMapPublishResult {
  recordType: string;
  version: number;
  unpackJobId: string;
}

export interface CrmJobSubmitted {
  jobId: string;
  status: string;
}

export interface CrmSyncRun {
  id: string;
  sourceFamily: string;
  syncMode: string;
  status: string;
  recordsScanned: number;
  recordsUpserted: number;
  recordsFailed: number;
  watermarkTo: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

export interface CrmResolvedPreview {
  recordType: string;
  columns: string[];
  rows: Record<string, string | null>[];
}

/** One record type a connection exposes + its lifecycle state (drives the left rail). */
export interface CrmDatasetSummary {
  recordType: string;
  sourceObject: string;
  status: string;
  version: number;
  hasSchedule: boolean;
  lastSyncAt: string | null;
}

export interface CrmRawSampleRecord {
  sourceRecordId: string;
  rawPayload: Record<string, unknown>;
}

export interface CrmRawSample {
  recordType: string;
  sourceObject: string;
  records: CrmRawSampleRecord[];
}

export interface CrmUnpackedSample {
  recordType: string;
  columns: string[];
  rows: Record<string, string | null>[];
}

export interface CrmFilterableField {
  field: string;
  operators: string[];
  pushable: boolean;
}

export interface CrmFilterCapabilities {
  recordType: string;
  sourceObject: string;
  fields: CrmFilterableField[];
}

/** Draft / activate request body: the in-progress bindings + optional filter predicate. */
export interface CrmDatasetDraftBody {
  recordType: string;
  bindings: CrmFieldBinding[];
  filterPredicate?: Record<string, unknown> | null;
}

export interface CrmDatasetDraftResult {
  recordType: string;
  status: string;
  version: number;
}

export interface CrmDatasetActivateResult {
  recordType: string;
  status: string;
  version: number;
  resolvedGrains: string[];
}

export interface CrmChainJob {
  id: string;
  jobType: string;
  status: string;
  createdAt: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

export interface CrmDatasetSchedule {
  id: string;
  name: string;
  cron: string;
  enabled: boolean;
  nextCheckAt: string | null;
  lastFireAt: string | null;
}

export interface CrmDatasetJobs {
  recordType: string;
  jobs: CrmChainJob[];
  schedule: CrmDatasetSchedule | null;
}

const base = (connectionId: string) => `/api/crm/connections/${connectionId}`;
const dataset = (connectionId: string, recordType: string) =>
  `${base(connectionId)}/datasets/${encodeURIComponent(recordType)}`;

export function getCrmGrains(): Promise<{ grains: CrmGrainSchema[] }> {
  return apiRequest('/api/crm/grains');
}

export function discoverCrmObjects(connectionId: string): Promise<{ objects: DiscoveredObject[] }> {
  return apiRequest(`${base(connectionId)}/objects`);
}

export function getCrmFieldMap(connectionId: string, recordType: string): Promise<CrmFieldMap> {
  return apiRequest(`${base(connectionId)}/field-maps?recordType=${encodeURIComponent(recordType)}`);
}

export function publishCrmFieldMap(
  connectionId: string,
  body: { recordType: string; bindings: CrmFieldBinding[] },
): Promise<CrmFieldMapPublishResult> {
  return apiRequest(`${base(connectionId)}/field-maps`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

export function getCrmFieldValues(
  connectionId: string,
  recordType: string,
  field: string,
): Promise<{ field: string; values: string[] }> {
  const q = `recordType=${encodeURIComponent(recordType)}&field=${encodeURIComponent(field)}`;
  return apiRequest(`${base(connectionId)}/field-values?${q}`);
}

export function triggerCrmSync(
  connectionId: string,
  sourceObjects?: string[],
): Promise<CrmJobSubmitted> {
  return apiRequest(`${base(connectionId)}/sync`, {
    method: 'POST',
    body: JSON.stringify(sourceObjects ? { sourceObjects } : {}),
  });
}

export function triggerCrmUnpack(connectionId: string): Promise<CrmJobSubmitted> {
  return apiRequest(`${base(connectionId)}/unpack`, { method: 'POST' });
}

export function getCrmSyncActivity(connectionId: string): Promise<{ runs: CrmSyncRun[] }> {
  return apiRequest(`${base(connectionId)}/sync-activity`);
}

export function getCrmResolvedPreview(
  connectionId: string,
  recordType: string,
): Promise<CrmResolvedPreview> {
  return apiRequest(`${base(connectionId)}/resolved-preview?recordType=${encodeURIComponent(recordType)}`);
}

export function listCrmDatasets(connectionId: string): Promise<{ datasets: CrmDatasetSummary[] }> {
  return apiRequest(`${base(connectionId)}/datasets`);
}

export function getCrmRawSample(connectionId: string, recordType: string): Promise<CrmRawSample> {
  return apiRequest(`${dataset(connectionId, recordType)}/raw-sample`);
}

export function getCrmUnpackedSample(
  connectionId: string,
  body: CrmDatasetDraftBody,
): Promise<CrmUnpackedSample> {
  return apiRequest(`${dataset(connectionId, body.recordType)}/unpacked-sample`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function getCrmFilterCapabilities(
  connectionId: string,
  recordType: string,
): Promise<CrmFilterCapabilities> {
  return apiRequest(`${dataset(connectionId, recordType)}/filter-capabilities`);
}

export function getCrmDatasetFieldValues(
  connectionId: string,
  recordType: string,
  field: string,
): Promise<{ field: string; values: string[] }> {
  return apiRequest(`${dataset(connectionId, recordType)}/field-values?field=${encodeURIComponent(field)}`);
}

export function saveCrmDatasetDraft(
  connectionId: string,
  body: CrmDatasetDraftBody,
): Promise<CrmDatasetDraftResult> {
  return apiRequest(`${dataset(connectionId, body.recordType)}/draft`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

export function getCrmDatasetJobs(connectionId: string, recordType: string): Promise<CrmDatasetJobs> {
  return apiRequest(`${dataset(connectionId, recordType)}/jobs`);
}

export function activateCrmDataset(
  connectionId: string,
  recordType: string,
): Promise<CrmDatasetActivateResult> {
  return apiRequest(`${dataset(connectionId, recordType)}/activate`, {
    method: 'POST',
    body: JSON.stringify({ recordType }),
  });
}

export function getCrmDatasetPreview(
  connectionId: string,
  recordType: string,
): Promise<CrmResolvedPreview> {
  return apiRequest(`${dataset(connectionId, recordType)}/preview`);
}
