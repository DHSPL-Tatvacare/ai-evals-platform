import { Fragment } from 'react';
import { ArrowRight } from 'lucide-react';

import { Card, ConnectionProviderLogo } from '@/components/ui';
import type { RunReportChannel } from '../types';
import { channelHeaderLabel } from './labels';

interface ClosedLoopRoutingProps {
  channels: RunReportChannel[];
}

/** Left-to-right routing strip: each channel is a step, arrows show how a
 *  contact flows from one channel to the next. Steps and labels are derived
 *  from `report.channels` order — no vendor or channel literal in code. */
export function ClosedLoopRouting({ channels }: ClosedLoopRoutingProps) {
  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Closed-loop routing</h3>
      {channels.length === 0 ? (
        <p className="py-4 text-center text-xs text-[var(--text-muted)]">No channels in this run</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {channels.map((channel, index) => {
            const first = channel.stages[0];
            const last = channel.stages[channel.stages.length - 1];
            return (
              <Fragment key={`${channel.capability}-${index}`}>
                <div className="flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-3 py-2">
                  {channel.vendor ? (
                    <ConnectionProviderLogo provider={channel.vendor} size={16} />
                  ) : null}
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-[var(--text-primary)]">
                      {channelHeaderLabel(channel)}
                    </p>
                    {first && last ? (
                      <p className="text-[11px] tabular-nums text-[var(--text-muted)]">
                        {first.label} {first.count} → {last.label} {last.count}
                      </p>
                    ) : null}
                  </div>
                </div>
                {index < channels.length - 1 ? (
                  <ArrowRight className="h-4 w-4 shrink-0 text-[var(--text-muted)]" aria-hidden />
                ) : null}
              </Fragment>
            );
          })}
        </div>
      )}
    </Card>
  );
}
