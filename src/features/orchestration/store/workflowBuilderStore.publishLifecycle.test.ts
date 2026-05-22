/**
 * Workflow-versioning redesign — store-level publish lifecycle.
 *
 * Covers the three-signal model that replaces the per-save version row:
 *   - `publishedDataHash` seeds on hydrate (from the live published def) and
 *     advances to the current snapshot on a successful publish.
 *   - reload-after-publish (hydrate from a `draftDefinition` that equals the
 *     live published def) settles to `clean-published` — the regression guard
 *     for the resurrected-deleted-node bug.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import type {
  WorkflowDefinition,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';
import { dataSnapshotHash } from '@/features/orchestration/contracts/snapshotHash';
import { deriveLifecycleState } from '@/features/orchestration/contracts/lifecycleState';
import { useWorkflowBuilderStore } from './workflowBuilderStore';

function node(id: string): WorkflowDefinitionNode {
  return {
    id,
    type: 'sink.complete',
    position: { x: 0, y: 0 },
    config: {},
  } as WorkflowDefinitionNode;
}

const liveDef: WorkflowDefinition = { nodes: [node('a')], edges: [] };

function lifecycleOf() {
  const s = useWorkflowBuilderStore.getState();
  return deriveLifecycleState({
    hasPublishedVersion: Boolean(s.currentPublishedVersionId),
    committedDataHash: s.committedDataHash,
    currentDataHash: s.currentDataHash,
    publishedDataHash: s.publishedDataHash,
    committedLayoutHash: s.committedLayoutHash,
    currentLayoutHash: s.currentLayoutHash,
    inFlight: s.inFlight,
    lastSaveOutcome: s.lastSaveOutcome,
    lastPublishOutcome: s.lastPublishOutcome,
  });
}

describe('workflowBuilderStore — publish lifecycle', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
  });

  it('seeds publishedDataHash from the published def passed to hydrate', () => {
    const liveHash = dataSnapshotHash(liveDef.nodes, liveDef.edges);
    useWorkflowBuilderStore
      .getState()
      .hydrate(liveDef, { publishedDataHash: liveHash });
    const s = useWorkflowBuilderStore.getState();
    expect(s.publishedDataHash).toBe(liveHash);
    expect(s.committedDataHash).toBe(liveHash);
    expect(s.currentDataHash).toBe(liveHash);
  });

  it('reload-after-publish: draft equals live → clean-published, canvas shows live def', () => {
    // Backend now hands the canvas `draftDefinition` (which equals the live
    // published def post-publish) plus the live published def for the hash.
    const liveHash = dataSnapshotHash(liveDef.nodes, liveDef.edges);
    useWorkflowBuilderStore.getState().setMetadata({
      workflowId: 'wf-1',
      versionId: null,
      name: 'WF',
      workflowType: 'crm',
      currentPublishedVersionId: 'ver-live',
    });
    useWorkflowBuilderStore
      .getState()
      .hydrate(liveDef, { publishedDataHash: liveHash });

    expect(lifecycleOf().kind).toBe('clean-published');
    // The canvas is the live def — no resurrected node.
    expect(useWorkflowBuilderStore.getState().nodes.map((n) => n.id)).toEqual([
      'a',
    ]);
  });

  it('finishPublish(ok) advances publishedDataHash to the current snapshot', () => {
    useWorkflowBuilderStore.getState().setMetadata({
      workflowId: 'wf-1',
      versionId: null,
      name: 'WF',
      workflowType: 'crm',
      currentPublishedVersionId: 'ver-1',
    });
    // Open on the live def, then add a node + commit it as a saved draft.
    const liveHash = dataSnapshotHash(liveDef.nodes, liveDef.edges);
    useWorkflowBuilderStore
      .getState()
      .hydrate(liveDef, { publishedDataHash: liveHash });
    useWorkflowBuilderStore.getState().addNode(node('b'));
    useWorkflowBuilderStore.getState().finishSave({ status: 'ok', at: 1 });

    // Saved but not published — draft diverges from live → publishable.
    expect(lifecycleOf().kind).toBe('dirty-published-edits');

    useWorkflowBuilderStore.getState().finishPublish({ status: 'ok', at: 2 });
    const s = useWorkflowBuilderStore.getState();
    expect(s.publishedDataHash).toBe(s.currentDataHash);
    expect(lifecycleOf().kind).toBe('clean-published');
  });

  it('finishPublish(fail) leaves publishedDataHash untouched', () => {
    useWorkflowBuilderStore.getState().setMetadata({
      workflowId: 'wf-1',
      versionId: null,
      name: 'WF',
      workflowType: 'crm',
      currentPublishedVersionId: 'ver-1',
    });
    const liveHash = dataSnapshotHash(liveDef.nodes, liveDef.edges);
    useWorkflowBuilderStore
      .getState()
      .hydrate(liveDef, { publishedDataHash: liveHash });
    useWorkflowBuilderStore.getState().addNode(node('b'));
    useWorkflowBuilderStore.getState().finishSave({ status: 'ok', at: 1 });
    const before = useWorkflowBuilderStore.getState().publishedDataHash;

    useWorkflowBuilderStore.getState().finishPublish({
      status: 'fail',
      at: 2,
      error: { kind: 'message', message: 'boom' },
    });
    expect(useWorkflowBuilderStore.getState().publishedDataHash).toBe(before);
  });
});
