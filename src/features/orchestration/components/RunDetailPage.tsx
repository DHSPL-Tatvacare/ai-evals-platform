import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

import { LoadingState } from '@/components/ui';
import { PageSurface } from '@/components/ui/PageSurface';
import { Tabs } from '@/components/ui/Tabs';
import { usePageMetadata } from '@/config/pageMetadata';
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
import { useRunStatusToasts } from '@/features/orchestration/hooks/useRunStatusToasts';
import { useOrchestrationRoutes } from '@/features/orchestration/hooks/useOrchestrationRoutes';
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
  const { icon, title } = usePageMetadata('campaigns');
  const orchestrationRoutes = useOrchestrationRoutes();
  const [loaded, setLoaded] = useState<LoadedState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useRunStream(runId);
  useRunStatusToasts(runId);

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
      <PageSurface icon={icon} title={title} showHeader={false} bleed>
        <div className="p-6 text-sm text-[var(--color-error)]">{error}</div>
      </PageSurface>
    );
  }
  if (!loaded) return <LoadingState />;

  const { run, workflow, version, nodeTypes } = loaded;

  return (
    <PageSurface icon={icon} title={title} showHeader={false} bleed>
      <div
        className="border-b px-5 py-3"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="flex items-baseline justify-between gap-3">
          <div className="flex flex-col gap-1">
            <Link
              to={orchestrationRoutes.campaignBuilder(workflow.id)}
              className="inline-flex w-fit items-center gap-1 text-[12px] font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>{workflow.name}</span>
            </Link>
            <div className="text-lg font-semibold text-[var(--text-primary)]">
              Run {run.id.slice(0, 8)}
            </div>
            <div className="text-xs text-[var(--text-secondary)]">
              {run.triggeredBy} · cohort {run.cohortSizeAtEntry}
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
    </PageSurface>
  );
}
