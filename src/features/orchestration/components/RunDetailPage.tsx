import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { LoadingState } from '@/components/ui';
import { Tabs } from '@/components/ui/Tabs';
import {
  fetchNodeTypes,
  getRun,
  getWorkflow,
  listVersions,
} from '@/services/api/orchestration';
import type {
  NodeTypeDescriptor,
  Workflow,
  WorkflowRun,
  WorkflowVersion,
} from '@/features/orchestration/types';
import { useRunStream } from '@/features/orchestration/hooks/useRunStream';
import { useRunOverlayStore } from '@/features/orchestration/store/runOverlayStore';
import { logger } from '@/services/logger';
import { ActionLogTab } from './ActionLogTab';
import { RecipientsTab } from './RecipientsTab';
import { RunCanvasOverlay } from './RunCanvasOverlay';

interface LoadedState {
  run: WorkflowRun;
  workflow: Workflow;
  version: WorkflowVersion;
  nodeTypes: NodeTypeDescriptor[];
}

/** Run detail page with three tabs: Canvas (live), Recipients, Action Log.
 *  Subscribes to the SSE stream for the lifetime of the page. */
export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [loaded, setLoaded] = useState<LoadedState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useRunStream(runId);

  const streamStatus = useRunOverlayStore((s) => s.streamStatus);
  const runStatus = useRunOverlayStore((s) => s.runStatus);

  const load = useCallback(async () => {
    if (!runId) return;
    setError(null);
    try {
      const run = await getRun(runId);
      const [workflow, versions, nodeTypes] = await Promise.all([
        getWorkflow(run.workflowId),
        listVersions(run.workflowId),
        fetchNodeTypes(),
      ]);
      const version = versions.find((v) => v.id === run.workflowVersionId) ?? null;
      if (!version) {
        setError('Workflow version not found for this run');
        return;
      }
      setLoaded({ run, workflow, version, nodeTypes });
    } catch (err) {
      logger.warn('RunDetailPage: load failed', { err: String(err) });
      setError(err instanceof Error ? err.message : 'Failed to load run');
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <div className="p-6 text-sm text-[var(--color-error)]">
        {error}
      </div>
    );
  }
  if (!loaded) return <LoadingState />;

  const { run, workflow, version, nodeTypes } = loaded;

  return (
    <div className="flex h-full flex-col">
      <div
        className="border-b px-4 py-3"
        style={{ borderColor: 'var(--border-default)' }}
      >
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <div className="text-lg font-semibold text-[var(--text-primary)]">
              {workflow.name}
            </div>
            <div className="text-xs text-[var(--text-secondary)]">
              Run {run.id.slice(0, 8)} · {run.triggeredBy} · cohort {run.cohortSizeAtEntry}
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-[var(--text-secondary)]">Run:</span>
            <span className="font-medium text-[var(--text-primary)]">{runStatus}</span>
            <span className="text-[var(--text-secondary)]">·</span>
            <span className="text-[var(--text-secondary)]">Stream:</span>
            <span className="font-medium text-[var(--text-primary)]">{streamStatus}</span>
          </div>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <Tabs
          fillHeight
          tabs={[
            {
              id: 'canvas',
              label: 'Canvas (Live)',
              content: (
                <RunCanvasOverlay
                  workflow={workflow}
                  version={version}
                  nodeTypesRegistry={nodeTypes}
                />
              ),
            },
            {
              id: 'recipients',
              label: 'Recipients',
              content: <RecipientsTab runId={run.id} />,
            },
            {
              id: 'log',
              label: 'Action Log',
              content: <ActionLogTab runId={run.id} />,
            },
          ]}
        />
      </div>
    </div>
  );
}
