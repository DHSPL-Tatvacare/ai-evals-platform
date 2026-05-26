import { useMemo } from 'react';
import { Loader2 } from 'lucide-react';
import { useRunOverlayStore } from '@/features/orchestration/store/runOverlayStore';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import type { WorkflowRun } from '@/features/orchestration/types';
import { cn } from '@/utils/cn';

interface CanvasRunIndicatorProps {
  liveRun: WorkflowRun | null;
  onOpen: () => void;
}

/** Persistent canvas chip shown while a run is in flight. Identity comes
 *  from the server-derived live run; progress from the SSE overlay store. */
export function CanvasRunIndicator({ liveRun, onOpen }: CanvasRunIndicatorProps) {
  const byNodeId = useRunOverlayStore((s) => s.byNodeId);
  const totalNodes = useWorkflowBuilderStore((s) => s.nodes.length);
  const completed = useMemo(
    () => Object.values(byNodeId).filter((n) => n.status === 'completed').length,
    [byNodeId],
  );
  if (!liveRun) return null;
  return (
    <button
      type="button"
      onClick={onOpen}
      title="Open run inspector"
      className={cn(
        'absolute left-1/2 top-3 z-[var(--z-sticky,10)] flex -translate-x-1/2 items-center gap-2',
        'rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated)]',
        'px-3 py-1 text-[12px] font-medium text-[var(--text-primary)] shadow-lg',
        'hover:border-[var(--border-default)]',
      )}
    >
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--color-warning)] opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--color-warning)]" />
      </span>
      <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--text-secondary)]" />
      <span>Run in progress</span>
      <span className="text-[var(--text-muted)]">
        {completed}/{totalNodes} nodes · {liveRun.id.slice(0, 8)}
      </span>
    </button>
  );
}
