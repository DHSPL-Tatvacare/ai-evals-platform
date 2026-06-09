export type StageState = 'done' | 'active' | 'todo';

export interface Stage {
  key: string;
  label: string;
  state: StageState;
}

/** Pure lineage state: Discover → Map → Publish → Resolved. No grain → no pipeline. */
export function computeStages(opts: {
  hasGrain: boolean;
  canPublish: boolean;
  publishedVersion: number;
  reprocessing: boolean;
}): Stage[] {
  if (!opts.hasGrain) return [];
  const published = opts.publishedVersion > 0;
  const resolved: StageState = published && !opts.reprocessing ? 'done' : opts.reprocessing ? 'active' : 'todo';
  return [
    { key: 'discover', label: 'Discover', state: 'done' },
    { key: 'map', label: 'Map fields', state: opts.canPublish ? 'done' : 'active' },
    { key: 'publish', label: 'Publish', state: published ? 'done' : opts.canPublish ? 'active' : 'todo' },
    { key: 'resolved', label: 'Resolved', state: resolved },
  ];
}
