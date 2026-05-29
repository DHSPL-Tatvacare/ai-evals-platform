import type { ReactNode } from 'react';

import { Card } from '@/components/ui';
import { ChartRenderer, CHART_PALETTE } from '@/features/analytics/components/ChartRenderer';
import { cn } from '@/utils/cn';
import type { RunReportResponse } from '../types';
import { ReportHeader } from './ReportHeader';
import { ChannelStatStrip } from './ChannelStatStrip';
import { EngagementFunnel } from './EngagementFunnel';
import { ClosedLoopRouting } from './ClosedLoopRouting';
import { RecipientTable } from './RecipientTable';

interface CampaignRunReportViewProps {
  report: RunReportResponse;
  printMode?: boolean;
  actions?: ReactNode;
}

const OUTCOME_SLICES: { key: keyof RunReportResponse['buckets']; name: string }[] = [
  { key: 'positive', name: 'Positive' },
  { key: 'reached', name: 'Reached' },
  { key: 'noResponse', name: 'No response' },
  { key: 'failed', name: 'Failed' },
  { key: 'inFlight', name: 'In flight' },
];

/** Donut + a matched legend (dot uses the same CHART_PALETTE var the slice gets,
 *  by index) carrying count + % of recipients — fills the row, no empty card. */
function OutcomeMix({ buckets }: { buckets: RunReportResponse['buckets'] }) {
  const data = OUTCOME_SLICES.map((slice) => ({
    name: slice.name,
    value: buckets[slice.key],
  })).filter((slice) => slice.value > 0);
  const total = data.reduce((sum, slice) => sum + slice.value, 0);

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Outcome mix</h3>
      {total === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--text-muted)]">No outcomes recorded</p>
      ) : (
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:gap-10">
          <div className="w-full sm:w-[280px] sm:shrink-0">
            <ChartRenderer
              type="donut"
              data={data}
              xKey="name"
              yKey="value"
              height={240}
              legendPosition="none"
              hideSliceLabels
            />
          </div>
          <ul className="flex w-full flex-1 flex-col justify-center gap-3">
            {data.map((slice, index) => {
              const pct = total ? Math.round((slice.value / total) * 100) : 0;
              return (
                <li key={slice.name} className="flex items-center gap-3 text-[13px]">
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: `var(${CHART_PALETTE[index % CHART_PALETTE.length]})` }}
                  />
                  <span className="flex-1 text-[var(--text-secondary)]">{slice.name}</span>
                  <span className="font-semibold tabular-nums text-[var(--text-primary)]">
                    {slice.value}
                  </span>
                  <span className="w-12 text-right tabular-nums text-[11px] text-[var(--text-muted)]">
                    {pct}%
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
  );
}

export function CampaignRunReportView({
  report,
  printMode = false,
  actions,
}: CampaignRunReportViewProps) {
  return (
    <div className={cn('space-y-4', printMode && 'space-y-5')}>
      <ReportHeader report={report} actions={actions} printMode={printMode} />

      {/* Channels present + their individual metrics. */}
      <div className="space-y-3">
        {report.channels.map((channel, index) => (
          <ChannelStatStrip
            key={`${channel.capability}-${index}`}
            channel={channel}
            printMode={printMode}
          />
        ))}
      </div>

      {/* Per-provider funnels, side by side, full width. */}
      <Card className="p-4">
        <h3 className="mb-4 text-sm font-semibold text-[var(--text-primary)]">Engagement funnel</h3>
        <EngagementFunnel channels={report.channels} printMode={printMode} />
      </Card>

      {/* Overall outcome mix. */}
      <OutcomeMix buckets={report.buckets} />

      <ClosedLoopRouting channels={report.channels} />

      <RecipientTable
        recipients={report.recipients}
        channels={report.channels}
        totalCount={report.recipientsTotalCount}
        printMode={printMode}
      />
    </div>
  );
}
