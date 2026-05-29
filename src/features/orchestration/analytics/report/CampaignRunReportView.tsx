import type { ReactNode } from 'react';

import { Card } from '@/components/ui';
import { ChartRenderer } from '@/features/analytics/components/ChartRenderer';
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

function OutcomeMix({ buckets }: { buckets: RunReportResponse['buckets'] }) {
  const data = OUTCOME_SLICES.map((slice) => ({
    name: slice.name,
    value: buckets[slice.key],
  })).filter((slice) => slice.value > 0);

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Outcome mix</h3>
      <ChartRenderer
        type="donut"
        data={data}
        xKey="name"
        yKey="value"
        height={240}
        legendPosition="right"
        hideSliceLabels
      />
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

      <div className="space-y-3">
        {report.channels.map((channel, index) => (
          <ChannelStatStrip
            key={`${channel.capability}-${index}`}
            channel={channel}
            printMode={printMode}
          />
        ))}
      </div>

      <div className={cn('grid gap-3', printMode ? 'grid-cols-1' : 'lg:grid-cols-2')}>
        <Card className="flex flex-col p-4">
          <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">
            Engagement funnel
          </h3>
          <EngagementFunnel channels={report.channels} printMode={printMode} />
        </Card>
        <OutcomeMix buckets={report.buckets} />
      </div>

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
