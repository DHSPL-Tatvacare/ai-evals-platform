import { useState } from 'react';
import { AlertCircle, Check, ChevronDown, Database, FileSearch, Loader2, Target } from 'lucide-react';
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
  return `${(ms / 1000).toFixed(2)} s`;
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
  const briefSummary = (part.briefSummary || part.summary || '').trim();
  const tablesCount = part.routing?.projectedTables?.length;
  const hasMetaRow = Boolean(projectedTable || rowCount !== undefined || evidenceCount || intentClass);

  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-2xl border bg-[var(--bg-elevated)] transition-all',
        compact ? 'border-transparent' : 'border-[var(--border-subtle)] shadow-[var(--shadow-sm)]',
        !compact && expandable && 'hover:shadow-[var(--shadow-default)]',
        isExecuting && 'border-[color-mix(in_srgb,var(--interactive-primary)_30%,var(--border-subtle))]',
        isError && 'border-[color-mix(in_srgb,var(--interactive-danger)_35%,var(--border-subtle))]',
      )}
    >
      {/* Left accent stripe — agent identity color */}
      <span
        aria-hidden
        className={cn(
          'absolute left-0 top-0 bottom-0 w-[3px]',
          isError ? 'bg-[var(--interactive-danger)]' : 'bg-[var(--interactive-primary)]',
          isExecuting && 'animate-pulse',
        )}
      />

      <button
        type="button"
        disabled={!expandable}
        onClick={() => expandable && setExpanded((v) => !v)}
        className={cn(
          'block w-full text-left transition-colors',
          'pl-4 pr-3 py-2.5',
          expandable && 'cursor-pointer hover:bg-[color-mix(in_srgb,var(--bg-secondary)_50%,transparent)]',
        )}
      >
        {/* Agent identity caps label */}
        <span className="flex items-center gap-2">
          <span className={cn(
            'inline-flex items-center gap-1 text-[9.5px] font-semibold uppercase tracking-[0.12em]',
            isError ? 'text-[var(--interactive-danger)]' : 'text-[var(--interactive-primary)]',
          )}>
            {label}
          </span>
          <span className="ml-auto flex shrink-0 items-center gap-2 text-[10.5px] text-[var(--text-muted)]">
            {isExecuting ? (
              <span className="inline-flex items-center gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                running
              </span>
            ) : isError ? (
              <span className="inline-flex items-center gap-1 text-[var(--interactive-danger)]">
                <AlertCircle className="h-3 w-3" />
                error
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[var(--color-verdict-pass)]">
                <Check className="h-3 w-3" />
                done
              </span>
            )}
            {duration && !isExecuting ? (
              <span className="font-mono tabular-nums">· {duration}</span>
            ) : null}
            {expandable ? (
              <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} />
            ) : null}
          </span>
        </span>

        {/* Narrative line */}
        <span className="mt-1 block text-[12.5px] text-[var(--text-primary)]">
          {isExecuting ? (
            <Shimmer>Sherlock is consulting the {label}…</Shimmer>
          ) : isError ? (
            <>Consultation failed</>
          ) : (
            <>Sherlock consulted the {label}</>
          )}
        </span>

        {/* Brief task summary line — what the supervisor asked */}
        {briefSummary && (isExecuting || isError) ? (
          <span className="mt-0.5 block text-[11px] italic text-[var(--text-muted)] line-clamp-2">
            {briefSummary}
          </span>
        ) : null}

        {/* Telemetry pill row */}
        {hasMetaRow ? (
          <span className="mt-2 flex flex-wrap items-center gap-1.5">
            {projectedTable ? (
              <ChipPill icon={Database} tone="brand" mono>
                {projectedTable}
                {tablesCount && tablesCount > 1 ? (
                  <span className="ml-1 text-[var(--text-muted)]">+{tablesCount - 1}</span>
                ) : null}
              </ChipPill>
            ) : null}
            {typeof rowCount === 'number' ? (
              <ChipPill tone="neutral">
                <span className="font-semibold tabular-nums">{rowCount}</span>
                <span className="text-[var(--text-muted)]">{rowCount === 1 ? 'row' : 'rows'}</span>
              </ChipPill>
            ) : null}
            {evidenceCount ? (
              <ChipPill icon={FileSearch} tone="success">
                <span className="font-semibold tabular-nums">{evidenceCount}</span>
                <span>evidence</span>
              </ChipPill>
            ) : null}
            {intentClass ? (
              <ChipPill icon={Target} tone="info">
                {intentClass}
              </ChipPill>
            ) : null}
          </span>
        ) : null}
      </button>

      {expanded && expandable ? (
        <div className="border-t border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-secondary)_60%,transparent)] pl-4">
          <div className="max-h-[44vh] overflow-y-auto px-3 py-3 text-[11px]">
            {part.routing ? (
              <dl className="mb-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
                {part.routing.intentClass ? (
                  <>
                    <dt className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Intent</dt>
                    <dd className="text-[var(--text-primary)]">{part.routing.intentClass}</dd>
                  </>
                ) : null}
                {part.routing.allowedLayers?.length ? (
                  <>
                    <dt className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Layers</dt>
                    <dd className="font-mono text-[var(--text-primary)]">{part.routing.allowedLayers.join(', ')}</dd>
                  </>
                ) : null}
                {part.routing.projectedTables?.length ? (
                  <>
                    <dt className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Tables</dt>
                    <dd className="font-mono text-[var(--text-primary)]">{part.routing.projectedTables.join(', ')}</dd>
                  </>
                ) : null}
                {part.routing.chartPayloadKind ? (
                  <>
                    <dt className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Result</dt>
                    <dd className="text-[var(--text-primary)]">{part.routing.chartPayloadKind}</dd>
                  </>
                ) : null}
                {part.routing.executionStatus && part.routing.executionStatus !== 'ok' ? (
                  <>
                    <dt className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Execution</dt>
                    <dd className="font-mono text-[var(--interactive-danger)]">{part.routing.executionStatus}</dd>
                  </>
                ) : null}
              </dl>
            ) : null}

            {part.detail?.error ? (
              <pre className="mb-3 whitespace-pre-wrap break-words rounded-lg bg-[color-mix(in_srgb,var(--interactive-danger)_8%,var(--bg-secondary))] p-2.5 font-mono text-[10.5px] text-[var(--interactive-danger)]">
                {part.detail.error}
              </pre>
            ) : null}

            {part.routing?.attemptedSql || part.detail?.sqlUsed ? (
              <div>
                <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">SQL</div>
                <pre className="whitespace-pre-wrap break-words rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-2.5 font-mono text-[10.5px] leading-relaxed text-[var(--text-primary)]">
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

interface ChipPillProps {
  children: React.ReactNode;
  icon?: typeof Database;
  tone?: 'brand' | 'neutral' | 'success' | 'info';
  mono?: boolean;
}

const TONE_PILL: Record<NonNullable<ChipPillProps['tone']>, string> = {
  brand: 'bg-[color-mix(in_srgb,var(--interactive-primary)_10%,transparent)] text-[var(--text-brand)] border-[color-mix(in_srgb,var(--interactive-primary)_22%,transparent)]',
  neutral: 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border-subtle)]',
  success: 'bg-[color-mix(in_srgb,var(--color-verdict-pass)_10%,transparent)] text-[var(--color-verdict-pass)] border-[color-mix(in_srgb,var(--color-verdict-pass)_22%,transparent)]',
  info: 'bg-[color-mix(in_srgb,var(--color-info)_10%,transparent)] text-[var(--color-info)] border-[color-mix(in_srgb,var(--color-info)_22%,transparent)]',
};

function ChipPill({ children, icon: Icon, tone = 'neutral', mono }: ChipPillProps) {
  return (
    <span className={cn(
      'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10.5px]',
      mono && 'font-mono',
      TONE_PILL[tone],
    )}>
      {Icon ? <Icon className="h-3 w-3" /> : null}
      {children}
    </span>
  );
}
