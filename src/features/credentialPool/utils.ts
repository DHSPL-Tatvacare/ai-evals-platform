import type { CredentialPoolConfig, CredentialPoolEntry, CredentialPoolEntrySource, CredentialPoolFieldConfig } from './types';

function isCredentialPoolEntry(
  entry: CredentialPoolEntry | Record<string, string>,
): entry is CredentialPoolEntry {
  return typeof (entry as CredentialPoolEntry).id === 'string' && typeof (entry as CredentialPoolEntry).values === 'object';
}

function createEntryId(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function createCredentialPoolEntry(
  values: Record<string, string>,
  source: CredentialPoolEntrySource = 'manual',
): CredentialPoolEntry {
  return {
    id: createEntryId(),
    values: Object.fromEntries(
      Object.entries(values).map(([key, value]) => [key, value.trim()]),
    ),
    source,
    testStatus: 'idle',
    testMessage: null,
  };
}

export function isCredentialEntryComplete(
  entry: CredentialPoolEntry,
  fields: CredentialPoolFieldConfig[],
): boolean {
  return fields
    .filter((field) => field.required !== false)
    .every((field) => Boolean(entry.values[field.key]?.trim()));
}

export function getCredentialEntrySignature(
  entry: CredentialPoolEntry | Record<string, string>,
  dedupeKeys: string[],
): string {
  const values = isCredentialPoolEntry(entry) ? entry.values : entry;
  return dedupeKeys.map((key) => values[key]?.trim().toLowerCase() ?? '').join('::');
}

export function mergeCredentialPoolEntries(
  existingEntries: CredentialPoolEntry[],
  incomingEntries: CredentialPoolEntry[],
  dedupeKeys: string[],
): CredentialPoolEntry[] {
  const seen = new Set(existingEntries.map((entry) => getCredentialEntrySignature(entry, dedupeKeys)));
  const merged = [...existingEntries];

  for (const entry of incomingEntries) {
    const signature = getCredentialEntrySignature(entry, dedupeKeys);
    if (!signature || seen.has(signature)) {
      continue;
    }
    seen.add(signature);
    merged.push(entry);
  }

  return merged;
}

export function dedupeCredentialPoolEntries(
  entries: CredentialPoolEntry[],
  dedupeKeys: string[],
): CredentialPoolEntry[] {
  return mergeCredentialPoolEntries([], entries, dedupeKeys);
}

export function getResolvedCredentialRows(
  entries: CredentialPoolEntry[],
  fields: CredentialPoolFieldConfig[],
): Array<Record<string, string>> {
  return entries
    .filter((entry) => isCredentialEntryComplete(entry, fields))
    .map((entry) => Object.fromEntries(
      fields.map((field) => [field.key, entry.values[field.key]?.trim() ?? '']),
    ));
}

export function buildCredentialPoolReviewSummary(
  entries: CredentialPoolEntry[],
  config: CredentialPoolConfig,
): { readyCount: number; primaryValues: string[] } {
  const resolvedRows = getResolvedCredentialRows(entries, config.fields);
  const primaryValues = resolvedRows
    .map((row) => row[config.primaryFieldKey])
    .filter(Boolean);

  return {
    readyCount: resolvedRows.length,
    primaryValues,
  };
}
