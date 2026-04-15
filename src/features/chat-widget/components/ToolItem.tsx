import { AlertCircle, Check, Loader2 } from 'lucide-react';
import { cn } from '@/utils/cn';
import { Shimmer } from './Shimmer';
import type { ToolCallPart } from '../types';

interface ToolItemProps {
  part: ToolCallPart;
  compact?: boolean;
}

export function ToolItem({ part, compact = false }: ToolItemProps) {
  const isExecuting = part.state === 'executing';
  const isError = part.state === 'error';

  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-xl border px-3 py-2 text-xs transition-colors',
        compact
          ? 'border-transparent bg-transparent px-0 py-1.5'
          : 'border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-secondary)_92%,transparent)]',
        isExecuting && 'border-[color-mix(in_srgb,var(--interactive-primary)_35%,transparent)] bg-[color-mix(in_srgb,var(--interactive-primary)_10%,var(--bg-secondary))]',
        isError && 'border-[color-mix(in_srgb,var(--interactive-danger)_40%,transparent)] bg-[color-mix(in_srgb,var(--interactive-danger)_10%,var(--bg-secondary))]',
      )}
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center">
        {isExecuting ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--interactive-primary)]" />
        ) : isError ? (
          <AlertCircle className="h-3.5 w-3.5 text-[var(--interactive-danger)]" />
        ) : (
          <Check className="h-3.5 w-3.5 text-[var(--color-verdict-pass)]" />
        )}
      </span>
      <span className="font-mono text-[11px] text-[var(--text-primary)]">{part.toolName}</span>
      <span className="ml-auto min-w-0 truncate text-[11px] text-[var(--text-muted)]">
        {isExecuting ? (
          <Shimmer>executing…</Shimmer>
        ) : isError ? (
          part.detail?.error ?? part.summary ?? 'failed'
        ) : (
          part.summary ?? 'done'
        )}
      </span>
      {typeof part.durationMs === 'number' && !isExecuting ? (
        <span className="shrink-0 font-mono text-[10px] text-[var(--text-muted)]">
          {Math.round(part.durationMs)}ms
        </span>
      ) : null}
    </div>
  );
}
