import { useState } from 'react';
import { AlertCircle, ChevronRight, Database, FileSearch, Loader2, Sparkles, Target } from 'lucide-react';
import { cn } from '@/utils/cn';
import { Shimmer } from './Shimmer';
import type { ToolCallPart } from '../types';

interface ToolItemProps {
  part: ToolCallPart;
  compact?: boolean;
}

const SPECIALIST_LABELS: Record<string, string> = {
  data_specialist: 'data specialist',
  retrieval_specialist: 'retrieval specialist',
  action_specialist: 'action specialist',
};

function formatDuration(ms?: number): string | null {
  if (typeof ms !== 'number' || ms < 0) return null;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function specialistLabel(name: string): string {
  return SPECIALIST_LABELS[name] ?? name.replace(/_/g, ' ');
}

export function ToolItem({ part, compact = false }: ToolItemProps) {
  const isExecuting = part.state === 'executing';
  const isError = part.state === 'error';
  const expandable = !isExecuting && (Boolean(part.detail) || Boolean(part.routing?.attemptedSql));
  const [expanded, setExpanded] = useState(false);

  const label = specialistLabel(part.toolName);
  const duration = formatDuration(part.durationMs);
  const projectedTable = part.routing?.projectedTables?.[0];
  const intentClass = part.routing?.intentClass;
  const rowCount = part.rowCount;
  const evidenceCount = part.evidenceCount;
  const briefSummary = part.briefSummary?.trim() || part.summary?.trim() || '';

  return (
    <div
      className={cn(
        'overflow-hidden rounded-xl border transition-colors',
        compact ? 'border-transparent' : 'border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-secondary)_92%,transparent)]',
        isExecuting && 'border-[color-mix(in_srgb,var(--interactive-primary)_30%,transparent)] bg-[color-mix(in_srgb,var(--interactive-primary)_8%,var(--bg-secondary))]',
        isError && 'border-[color-mix(in_srgb,var(--interactive-danger)_40%,transparent)] bg-[color-mix(in_srgb,var(--interactive-danger)_8%,var(--bg-secondary))]',
      )}
    >
      <button
        type="button"
        disabled={!expandable}
        onClick={() => expandable && setExpanded((v) => !v)}
        className={cn(
          'flex w-full flex-col gap-1.5 px-3 py-2.5 text-left transition-colors',
          compact && 'px-0 py-1.5',
          expandable && 'cursor-pointer hover:bg-[color-mix(in_srgb,var(--bg-secondary)_60%,transparent)]',
        )}
      >
        {/* Title row: status icon + narrative + duration + chevron */}
        <span className="flex items-center gap-2">
          <span className="flex h-4 w-4 shrink-0 items-center justify-center">
            {isExecuting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--interactive-primary)]" />
            ) : isError ? (
              <AlertCircle className="h-3.5 w-3.5 text-[var(--interactive-danger)]" />
            ) : (
              <Sparkles className="h-3.5 w-3.5 text-[var(--interactive-primary)]" />
            )}
          </span>
          <span className="min-w-0 flex-1 text-[12px] text-[var(--text-primary)]">
            {isExecuting ? (
              <Shimmer>Sherlock is consulting the {label}…</Shimmer>
            ) : isError ? (
              <>Sherlock's <span className="font-medium">{label}</span> hit an error</>
            ) : (
              <>Sherlock consulted the <span className="font-medium">{label}</span></>
            )}
          </span>
          {duration && !isExecuting ? (
            <span className="shrink-0 font-mono text-[10px] text-[var(--text-muted)]">{duration}</span>
          ) : null}
          {expandable ? (
            <ChevronRight className={cn('h-3 w-3 shrink-0 text-[var(--text-muted)] transition-transform', expanded && 'rotate-90')} />
          ) : null}
        </span>

        {/* Brief task summary — what the supervisor asked for */}
        {briefSummary && (isExecuting || isError) ? (
          <span className="block pl-6 pr-1 text-[11px] text-[var(--text-muted)] line-clamp-2">
            {briefSummary}
          </span>
        ) : null}

        {/* Telemetry chip row (Phase 1A): table · rows · evidence · intent */}
        {!isExecuting && (projectedTable || rowCount !== undefined || evidenceCount || intentClass) ? (
          <span className="flex flex-wrap items-center gap-1.5 pl-6 text-[10.5px] text-[var(--text-muted)]">
            {projectedTable ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-[var(--bg-primary)] px-1.5 py-0.5 font-mono">
                <Database className="h-3 w-3" />
                {projectedTable}
              </span>
            ) : null}
            {typeof rowCount === 'number' ? (
              <span className="inline-flex items-center rounded-md bg-[var(--bg-primary)] px-1.5 py-0.5">
                {rowCount} {rowCount === 1 ? 'row' : 'rows'}
              </span>
            ) : null}
            {evidenceCount ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-[var(--bg-primary)] px-1.5 py-0.5">
                <FileSearch className="h-3 w-3" />
                {evidenceCount} {evidenceCount === 1 ? 'evidence' : 'evidence'}
              </span>
            ) : null}
            {intentClass ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-[var(--bg-primary)] px-1.5 py-0.5">
                <Target className="h-3 w-3" />
                {intentClass}
              </span>
            ) : null}
          </span>
        ) : null}
      </button>

      {expanded && expandable ? (
        <div className="border-t border-[var(--border-default)] bg-[var(--bg-primary)]">
          <div className="max-h-[40vh] overflow-y-auto p-3 text-[11px]">
            {/* Routing context: intent, projected layers, allowed tables */}
            {part.routing ? (
              <div className="mb-3 flex flex-wrap gap-x-3 gap-y-1 text-[var(--text-muted)]">
                {part.routing.intentClass ? (
                  <span>Intent <strong className="text-[var(--text-primary)]">{part.routing.intentClass}</strong></span>
                ) : null}
                {part.routing.allowedLayers?.length ? (
                  <span>Layers <strong className="font-mono text-[var(--text-primary)]">{part.routing.allowedLayers.join(', ')}</strong></span>
                ) : null}
                {part.routing.projectedTables?.length ? (
                  <span>Tables <strong className="font-mono text-[var(--text-primary)]">{part.routing.projectedTables.join(', ')}</strong></span>
                ) : null}
                {part.routing.chartPayloadKind ? (
                  <span>Result <strong className="text-[var(--text-primary)]">{part.routing.chartPayloadKind}</strong></span>
                ) : null}
              </div>
            ) : null}

            {part.detail?.error ? (
              <pre className="mt-2 whitespace-pre-wrap break-words rounded bg-[color-mix(in_srgb,var(--interactive-danger)_8%,var(--bg-secondary))] p-2 font-mono text-[10px] text-[var(--interactive-danger)]">
                {part.detail.error}
              </pre>
            ) : null}

            {part.routing?.attemptedSql || part.detail?.sqlUsed ? (
              <div className="mt-1">
                <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">SQL</div>
                <pre className="whitespace-pre-wrap break-words rounded bg-[var(--bg-secondary)] p-2 font-mono text-[10px] text-[var(--text-primary)]">
                  {part.routing?.attemptedSql ?? part.detail?.sqlUsed}
                </pre>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
