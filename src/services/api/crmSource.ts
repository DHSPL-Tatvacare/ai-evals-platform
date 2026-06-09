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

const base = (connectionId: string) => `/api/crm/connections/${connectionId}`;

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
