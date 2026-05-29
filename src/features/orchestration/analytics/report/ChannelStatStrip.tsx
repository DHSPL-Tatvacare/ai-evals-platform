import { Card, ConnectionProviderLogo } from '@/components/ui';
import { cn } from '@/utils/cn';
import type { RunReportChannel } from '../types';
import { channelHeaderLabel } from './labels';
import { formatDuration, formatPct } from '../format';

interface ChannelStatStripProps {
  channel: RunReportChannel;
  printMode?: boolean;
}

/** Per-channel metric strip: stage counts (data-driven labels) plus voice talk
 *  time when the channel reports it. One strip renders per `report.channels`
 *  entry — never branches on a vendor or capability literal. */
export function ChannelStatStrip({ channel, printMode = false }: ChannelStatStripProps) {
  const baseline = channel.stages[0]?.count ?? 0;
  const avgTalk = channel.metrics.avgDurationSec;
  const totalTalk = channel.metrics.totalDurationSec;

  return (
    <Card className={cn('p-4', printMode && 'shadow-none')}>
      <div className="mb-3 flex items-center gap-2">
        {channel.vendor ? (
          <ConnectionProviderLogo provider={channel.vendor} size={18} />
        ) : null}
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          {channelHeaderLabel(channel)}
        </h3>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {channel.stages.map((stage) => (
          <div key={stage.key}>
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
              {stage.label}
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
              {stage.count}
            </p>
            {baseline > 0 ? (
              <p className="text-[11px] tabular-nums text-[var(--text-muted)]">
                {formatPct(stage.count, baseline)} of {channel.stages[0]?.label.toLowerCase()}
              </p>
            ) : null}
          </div>
        ))}
        {typeof avgTalk === 'number' ? (
          <div>
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
              Avg talk time
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
              {formatDuration(avgTalk)}
            </p>
          </div>
        ) : null}
        {typeof totalTalk === 'number' ? (
          <div>
            <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
              Total talk time
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
              {formatDuration(totalTalk)}
            </p>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
