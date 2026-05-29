import type { ReactNode } from 'react';

import { cn } from '@/utils/cn';
import type { RunReportResponse } from '../types';
import { formatDuration } from '../format';
import { distinctChannelNames, joinChannelNames } from './labels';

interface ReportHeaderProps {
  report: RunReportResponse;
  actions?: ReactNode;
  printMode?: boolean;
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function HeaderField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

export function ReportHeader({ report, actions, printMode = false }: ReportHeaderProps) {
  const channelNames = joinChannelNames(distinctChannelNames(report.channels));
  const subtitle = channelNames
    ? `${report.recipientsTotal} contacts across ${channelNames}`
    : `${report.recipientsTotal} contacts`;

  const totalTalkSec = report.channels.reduce(
    (sum, channel) => sum + (channel.metrics.totalDurationSec ?? 0),
    0,
  );
  const duration =
    typeof report.durationSeconds === 'number' ? formatDuration(report.durationSeconds) : '—';

  return (
    <div
      className={cn(
        'rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3',
        printMode && 'bg-transparent shadow-none',
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            {report.workflowName}
          </h2>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">{subtitle}</p>
        </div>
        {!printMode && actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <HeaderField label="Status" value={report.status} />
        <HeaderField label="Started" value={formatDate(report.startedAt)} />
        <HeaderField label="Duration" value={duration} />
        <HeaderField label="Talk time" value={formatDuration(totalTalkSec)} />
      </div>
    </div>
  );
}
