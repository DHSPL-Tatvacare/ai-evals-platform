import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';

import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { LoadingState } from '@/components/ui/LoadingState';
import { PageSurface } from '@/components/ui/PageSurface';
import { usePageMetadata } from '@/config/pageMetadata';
import { ApiError } from '@/services/api/client';
import { getWorkflow, listVersions } from '@/services/api/orchestration';
import type { WorkflowRun } from '@/features/orchestration/types';
import { notificationService } from '@/services/notifications';
import { useRunStream } from '@/features/orchestration/hooks/useRunStream';
import { useRunStatusToasts } from '@/features/orchestration/hooks/useRunStatusToasts';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import { Canvas } from './Canvas';
import { NodeConfigPanel } from './NodeConfigPanel';
import { Palette } from './Palette';
import { WorkflowHeaderBar } from './WorkflowHeaderBar';

export function WorkflowBuilderPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const { icon, title } = usePageMetadata('campaigns');
  const [activeRun, setActiveRun] = useState<WorkflowRun | null>(null);
  const reset = useWorkflowBuilderStore((s) => s.reset);
  const setMetadata = useWorkflowBuilderStore((s) => s.setMetadata);
  const hydrate = useWorkflowBuilderStore((s) => s.hydrate);
  const selectedNodeId = useWorkflowBuilderStore((s) => s.selectedNodeId);
  const clearSelection = useWorkflowBuilderStore((s) => s.clearSelection);
  const pendingDeleteNodeId = useWorkflowBuilderStore((s) => s.pendingDeleteNodeId);
  const cancelDeleteNode = useWorkflowBuilderStore((s) => s.cancelDeleteNode);
  const removeNode = useWorkflowBuilderStore((s) => s.removeNode);
  const pendingDeleteNode = useWorkflowBuilderStore((s) =>
    s.nodes.find((n) => n.id === s.pendingDeleteNodeId) ?? null,
  );

  useEffect(() => {
    if (!workflowId) return;
    let alive = true;
    (async () => {
      reset();
      try {
        const wf = await getWorkflow(workflowId);
        const versions = await listVersions(workflowId);
        const draft = versions.find((v) => v.status === 'draft');
        const targetVersion = draft ?? versions[0] ?? null;
        if (!alive) return;
        setMetadata({
          workflowId: wf.id,
          versionId: targetVersion?.id ?? null,
          name: wf.name,
          workflowType: wf.workflowType,
          currentPublishedVersionId: wf.currentPublishedVersionId,
        });
        if (targetVersion) {
          hydrate(targetVersion.definition);
        }
      } catch (e) {
        if (!alive) return;
        const msg =
          e instanceof ApiError
            ? e.message
            : e instanceof Error
              ? e.message
              : 'Failed to load workflow';
        notificationService.error(msg);
      }
    })();
    return () => {
      alive = false;
    };
  }, [workflowId, reset, setMetadata, hydrate]);

  // ESC clears selection so the inspector unmounts. The pane click handler
  // covers the canvas-click case (see Canvas.tsx).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && selectedNodeId !== null) clearSelection();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [selectedNodeId, clearSelection]);

  if (!workflowId) return <LoadingState />;

  // Live run state renders directly on the builder canvas (node status
  // pills + edge traversal highlights via ``Canvas``'s ``activeRunId``
  // prop). The session hooks below own the SSE stream and toast surface
  // — no panel, no split, no second canvas. Phase-13 UX rule.
  const liveRunId =
    activeRun && activeRun.workflowId === workflowId ? activeRun.id : undefined;

  return (
    <>
    <PageSurface icon={icon} title={title} showHeader={false} bleed>
      <WorkflowHeaderBar onRunStarted={setActiveRun} />
      <RunSession runId={liveRunId} />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <Palette />
          <div className="min-w-0 flex-1">
            <Canvas activeRunId={liveRunId} />
          </div>
          <AnimatePresence initial={false}>
            {selectedNodeId !== null ? (
              <motion.div
                key="inspector"
                initial={{ x: 16, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: 16, opacity: 0 }}
                transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                className="h-full flex-shrink-0"
              >
                <NodeConfigPanel />
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </div>
    </PageSurface>
    <ConfirmDialog
      isOpen={pendingDeleteNodeId !== null}
      onClose={cancelDeleteNode}
      onConfirm={() => {
        if (pendingDeleteNodeId) removeNode(pendingDeleteNodeId);
        cancelDeleteNode();
      }}
      title="Remove node from canvas?"
      description={
        pendingDeleteNode
          ? `Remove "${(pendingDeleteNode.data?.label as string) ?? pendingDeleteNode.type}" and any edges connected to it. This affects the draft only — the change is undone if you reload without saving.`
          : ''
      }
      confirmLabel="Remove"
      variant="danger"
    />
    </>
  );
}

/** Invisible host for the per-run side-effects: SSE stream that drives
 *  ``runOverlayStore`` (which the builder ``Canvas`` reads for node
 *  pills + edge highlights) and the toast surface for run.started /
 *  run.completed / run.failed. Mounted once when a run is in flight on
 *  the current workflow; unmounts (and tears the stream down) when the
 *  run is dismissed or the user switches workflow. */
function RunSession({ runId }: { runId: string | undefined }) {
  useRunStream(runId);
  useRunStatusToasts(runId);
  return null;
}
