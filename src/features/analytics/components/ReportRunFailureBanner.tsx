import { Ban, XCircle } from 'lucide-react';
import { cn } from '@/utils';

interface Props {
  /** Terminal status of the most recent report run — 'failed' or 'cancelled'. */
  status: 'failed' | 'cancelled';
  /**
   * The real failure reason surfaced from the report run's job
   * (`Job.errorMessage`). When absent we fall back to a generic line so the
   * banner still explains the outcome.
   */
  errorMessage?: string | null;
  className?: string;
}

const GENERIC_FAILURE =
  'The last cross-run report failed. Cross-run reports aggregate your existing single-run reports — generate those first, then try again.';

/**
 * Failure/cancelled banner for the cross-run report surface. Renders the real
 * reason from the job's error message and only falls back to a generic line
 * when no reason is available. Mirrors `RunStatusBanner` styling so failure
 * states look consistent across the app.
 */
export function ReportRunFailureBanner({ status, errorMessage, className }: Props) {
  if (status === 'cancelled') {
    return (
      <div
        className={cn(
          'rounded-md border border-[var(--border-warning)] bg-[var(--surface-warning)] px-4 py-2.5',
          className,
        )}
      >
        <div className="flex items-center gap-2 text-[var(--color-warning)]">
          <Ban className="h-4 w-4 shrink-0" />
          <strong className="text-sm font-medium">Cross-run report cancelled</strong>
        </div>
        {errorMessage ? (
          <p className="mt-1 text-xs leading-5 text-[var(--color-warning)]" style={{ opacity: 0.85 }}>
            {errorMessage}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div
      className={cn(
        'rounded-md border border-[var(--border-error)] bg-[var(--surface-error)] px-4 py-2.5',
        className,
      )}
    >
      <div className="flex items-center gap-2 text-[var(--color-error)]">
        <XCircle className="h-4 w-4 shrink-0" />
        <strong className="text-sm font-medium">Cross-run report failed</strong>
      </div>
      <p className="mt-1 text-xs leading-5 text-[var(--color-error)]" style={{ opacity: 0.85 }}>
        {errorMessage || GENERIC_FAILURE}
      </p>
    </div>
  );
}
