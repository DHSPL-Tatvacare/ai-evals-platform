import { useEffect, type CSSProperties, useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, Loader2, Radio, X } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { LoadingState } from '@/components/ui/LoadingState';
import { Tabs } from '@/components/ui/Tabs';
import { fetchNodeTypes, getRun, getWorkflow, listVersions } from '@/services/api/orchestration';
import type {
  NodeTypeDescriptor,
  RunStatus,
  Workflow,
  WorkflowRun,
  WorkflowVersion,
} from '@/features/orchestration/types';
import { isRunActive } from '@/features/orchestration/types';
import {
  useRunOverlayStore,
  type RunStreamStatus,
} from '@/features/orchestration/store/runOverlayStore';
import { useRunStatusToasts } from '@/features/orchestration/hooks/useRunStatusToasts';
import { useRunStream } from '@/features/orchestration/hooks/useRunStream';
import { useOrchestrationRoutes } from '@/features/orchestration/hooks/useOrchestrationRoutes';
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

interface BuilderLiveRunPanelProps {
  runId: string;
  onClose: () => void;
}

export function BuilderLiveRunPanel({ runId, onClose }: BuilderLiveRunPanelProps) {
  const orchestrationRoutes = useOrchestrationRoutes();
  const [loaded, setLoaded] = useState<LoadedState | null>(null);
  const [error, setError] = useState<{ runId: string; message: string } | null>(null);

  useRunStream(runId);
  useRunStatusToasts(runId);

  const overlayRunId = useRunOverlayStore((s) => s.runId);
  const hydrated = useRunOverlayStore((s) => s.hydrated);
  const streamStatus = useRunOverlayStore((s) => s.streamStatus);
  const runStatus = useRunOverlayStore((s) => s.runStatus);
  const overlayByNodeId = useRunOverlayStore((s) => s.byNodeId);

  useEffect(() => {
    let alive = true;

    void (async () => {
      try {
        const run = await getRun(runId);
        const [workflow, versions, nodeTypes] = await Promise.all([
          getWorkflow(run.workflowId),
          listVersions(run.workflowId),
          fetchNodeTypes(),
        ]);
        if (!alive) return;
        const version = versions.find((candidate) => candidate.id === run.workflowVersionId) ?? null;
        if (!version) {
          setError({ runId, message: 'Workflow version not found for this run' });
          return;
        }
        setError(null);
        setLoaded({ run, workflow, version, nodeTypes });
      } catch (err) {
        if (!alive) return;
        logger.warn('BuilderLiveRunPanel: load failed', { err: String(err) });
        setError({
          runId,
          message: err instanceof Error ? err.message : 'Failed to load run',
        });
      }
    })();

    return () => {
      alive = false;
    };
  }, [runId]);

  if (error?.runId === runId) {
    return (
      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="text-sm text-[var(--color-error)]">{error.message}</div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    );
  }

  if (!loaded || loaded.run.id !== runId) {
    return (
      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
        <LoadingState />
      </div>
    );
  }

  const { run, version, nodeTypes } = loaded;
  const displayRunStatus = overlayRunId === run.id && hydrated ? runStatus : run.status;
  const liveLabel = getStreamLabel(streamStatus, displayRunStatus);
  const liveTone = getStreamTone(streamStatus, displayRunStatus);
  const states = Object.values(overlayByNodeId);
  const progress = {
    total: version.definition.nodes.length,
    completed: states.filter(
      (state) => state.status === 'completed' || state.status === 'skipped',
    ).length,
    running: states.filter((state) => state.status === 'running').length,
    failed: states.filter((state) => state.status === 'failed').length,
  };

  return (
    <div className="flex min-h-[320px] max-h-[420px] flex-col border-t border-[var(--border-subtle)] bg-[var(--bg-primary)]">
      <div className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-[var(--text-primary)]">
              Live test run {run.id.slice(0, 8)}
            </span>
            <Badge variant={getRunBadgeVariant(displayRunStatus)}>{displayRunStatus}</Badge>
            <span
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
              style={liveTone}
            >
              {streamStatus === 'open' ? (
                <Radio className="h-3.5 w-3.5" />
              ) : streamStatus === 'connecting' || streamStatus === 'reconnecting' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Radio className="h-3.5 w-3.5" />
              )}
              <span>{liveLabel}</span>
            </span>
          </div>
          <div className="mt-1 text-xs text-[var(--text-secondary)]">
            Testing published version v{version.version}. You can stay in the builder and
            keep editing separately; this panel tracks the run that is already in flight.
          </div>
          <div className="mt-2 text-[11px] text-[var(--text-secondary)]">
            {progress.completed}/{progress.total} nodes finished
            {progress.running > 0 ? ` · ${progress.running} running` : ''}
            {progress.failed > 0 ? ` · ${progress.failed} failed` : ''}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link to={orchestrationRoutes.campaignRunDetail(run.id)}>
            <Button variant="secondary" size="sm">
              <ExternalLink className="mr-1 h-3.5 w-3.5" />
              Open run
            </Button>
          </Link>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="mr-1 h-3.5 w-3.5" />
            Close
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 px-3 pb-3">
        <Tabs
          fillHeight
          tabs={[
            {
              id: 'canvas',
              label: 'Canvas (Live)',
              content: (
                <RunCanvasOverlay version={version} nodeTypesRegistry={nodeTypes} />
              ),
            },
            {
              id: 'recipients',
              label: 'Recipients',
              content: <RecipientsTab runId={run.id} runStatus={displayRunStatus} />,
            },
            {
              id: 'log',
              label: 'Action Log',
              content: <ActionLogTab runId={run.id} runStatus={displayRunStatus} />,
            },
          ]}
        />
      </div>
    </div>
  );
}

function getRunBadgeVariant(status: RunStatus): 'neutral' | 'info' | 'warning' | 'success' | 'error' {
  switch (status) {
    case 'running':
      return 'info';
    case 'waiting':
      return 'warning';
    case 'completed':
      return 'success';
    case 'failed':
      return 'error';
    default:
      return 'neutral';
  }
}

function getStreamLabel(streamStatus: RunStreamStatus, runStatus: RunStatus): string {
  if (!isRunActive(runStatus)) {
    return 'Final state';
  }
  switch (streamStatus) {
    case 'open':
      return 'Live';
    case 'connecting':
      return 'Connecting…';
    case 'reconnecting':
      return 'Reconnecting…';
    case 'error':
      return 'Retrying…';
    case 'closed':
      return 'Paused';
    default:
      return 'Preparing…';
  }
}

function getStreamTone(streamStatus: RunStreamStatus, runStatus: RunStatus): CSSProperties {
  if (!isRunActive(runStatus)) {
    return {
      backgroundColor: 'var(--bg-tertiary)',
      color: 'var(--text-secondary)',
    };
  }
  if (streamStatus === 'open') {
    return {
      backgroundColor: 'var(--surface-success)',
      color: 'var(--color-success)',
    };
  }
  if (streamStatus === 'error' || streamStatus === 'reconnecting') {
    return {
      backgroundColor: 'var(--surface-warning)',
      color: 'var(--color-warning)',
    };
  }
  return {
    backgroundColor: 'var(--surface-info)',
    color: 'var(--color-info)',
  };
}
