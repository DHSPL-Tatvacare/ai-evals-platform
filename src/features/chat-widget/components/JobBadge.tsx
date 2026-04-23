import { useEffect, useRef } from 'react';
import { CheckCircle2, Clock, Loader2, XCircle } from 'lucide-react';

import { cn } from '@/utils/cn';

import { pollJobUntilComplete } from '@/services/api/jobPolling';
import type { JobBadgePart, JobBadgeStatus } from '../types';

interface JobBadgeProps {
  part: JobBadgePart;
  /** Called with the updated status when the backend transitions the job. */
  onStatusChange?: (next: Pick<JobBadgePart, 'status' | 'resultHref'>) => void;
}

const TERMINAL: ReadonlySet<JobBadgeStatus> = new Set(['completed', 'failed', 'cancelled']);

function statusMeta(status: JobBadgeStatus) {
  if (status === 'completed') {
    return {
      Icon: CheckCircle2,
      label: 'Completed',
      classes: 'border-[var(--border-success)] bg-[var(--surface-success)] text-[var(--color-verdict-pass)]',
      spin: false,
    };
  }
  if (status === 'failed' || status === 'cancelled') {
    return {
      Icon: XCircle,
      label: status === 'failed' ? 'Failed' : 'Cancelled',
      classes:
        'border-[color-mix(in_srgb,var(--interactive-danger)_40%,transparent)] bg-[color-mix(in_srgb,var(--interactive-danger)_8%,var(--bg-primary))] text-[var(--interactive-danger)]',
      spin: false,
    };
  }
  if (status === 'running') {
    return {
      Icon: Loader2,
      label: 'Running',
      classes: 'border-[var(--border-primary)] bg-[var(--bg-secondary)] text-[var(--text-primary)]',
      spin: true,
    };
  }
  return {
    Icon: Clock,
    label: 'Queued',
    classes: 'border-[var(--border-primary)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]',
    spin: false,
  };
}

// Phase 7 — async jobs as first-class harness outcomes.
// Reuses ``pollJobUntilComplete`` (no new polling primitive per plan §804).
export function JobBadge({ part, onStatusChange }: JobBadgeProps) {
  const meta = statusMeta(part.status);
  const pollingStartedRef = useRef<string | null>(null);

  useEffect(() => {
    if (TERMINAL.has(part.status)) return;
    // Poll exactly once per job id; avoid duplicate polls on rerender.
    if (pollingStartedRef.current === part.jobId) return;
    pollingStartedRef.current = part.jobId;

    const controller = new AbortController();
    pollJobUntilComplete(part.jobId, { signal: controller.signal })
      .then((job) => {
        onStatusChange?.({
          status: job.status as JobBadgeStatus,
          resultHref: part.resultHref,
        });
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        onStatusChange?.({ status: 'failed', resultHref: part.resultHref });
      });

    return () => {
      controller.abort();
    };
  }, [part.jobId, part.status, part.resultHref, onStatusChange]);

  return (
    <div
      className={cn(
        'flex items-center gap-2.5 rounded-xl border px-3 py-2 text-xs',
        meta.classes,
      )}
    >
      <meta.Icon className={cn('h-3.5 w-3.5 shrink-0', meta.spin && 'animate-spin')} />
      <div className="min-w-0 flex-1">
        <div className="font-semibold">{meta.label}</div>
        {part.summary ? (
          <div className="truncate text-[11px] opacity-80">{part.summary}</div>
        ) : null}
      </div>
      {part.status === 'completed' && part.resultHref ? (
        <a
          href={part.resultHref}
          className="shrink-0 rounded-lg border border-current px-2 py-0.5 text-[11px] font-semibold transition-opacity hover:opacity-100"
        >
          View
        </a>
      ) : null}
    </div>
  );
}
