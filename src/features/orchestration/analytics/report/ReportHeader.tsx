import type { ReactNode } from 'react';

import type { RunReportResponse } from '../types';
import { formatDuration } from '../format';
import { distinctChannelNames, joinChannelNames } from './labels';

interface ReportHeaderProps {
  report: RunReportResponse;
  actions?: ReactNode;
  printMode?: boolean;
}

/** Brand-gradient report banner, matching the platform eval-report header. White
 *  text is intentional on the brand gradient (mirrors the Cost AI banner). The
 *  gradient is kept in printMode so the PDF header matches the on-screen report. */
const BANNER_GRADIENT =
  'linear-gradient(135deg, var(--color-brand-primary) 0%, var(--color-brand-primary-hover) 55%, var(--color-brand-primary-deep) 100%)';

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

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <span className="whitespace-nowrap">
      <span className="text-white/60">{label}</span> {value}
    </span>
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
      className="overflow-hidden rounded-lg text-white shadow-[var(--shadow-md)]"
      style={{ background: BANNER_GRADIENT }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4 px-5 py-4">
        <div className="min-w-0">
          <h2 className="truncate text-xl font-bold tracking-tight">{report.workflowName}</h2>
          <p className="mt-1 text-[13px] font-medium text-white/85">{subtitle}</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] text-white/85">
            <MetaItem label="Started" value={formatDate(report.startedAt)} />
            <MetaItem label="Duration" value={duration} />
            <MetaItem label="Talk time" value={formatDuration(totalTalkSec)} />
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide">
            {report.status}
          </span>
          {!printMode && actions ? <div>{actions}</div> : null}
        </div>
      </div>
    </div>
  );
}
