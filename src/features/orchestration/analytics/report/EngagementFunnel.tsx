import { ConnectionProviderLogo, Funnel } from '@/components/ui';
import { cn } from '@/utils/cn';
import type { RunReportChannel } from '../types';
import { channelHeaderLabel } from './labels';

interface EngagementFunnelProps {
  channels: RunReportChannel[];
  printMode?: boolean;
}

/** One true funnel per channel — never clubbed, laid out side-by-side so each
 *  funnel has full width for un-truncated labels. Each channel's own root-first
 *  stage list (from the API) drives its funnel; labels/counts come only from
 *  `channel.stages`, so a new channel renders with no code change. */
export function EngagementFunnel({ channels, printMode = false }: EngagementFunnelProps) {
  const multiChannel = channels.length > 1;
  return (
    <div
      className={cn(
        'grid gap-x-8 gap-y-6',
        !printMode && multiChannel ? 'sm:grid-cols-2' : 'grid-cols-1',
      )}
    >
      {channels.map((channel, index) => (
        <section key={`${channel.capability}-${index}`} className="flex flex-col gap-3">
          <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] pb-2">
            {channel.vendor && (
              <ConnectionProviderLogo provider={channel.vendor} size={18} />
            )}
            <h4 className="text-[13px] font-semibold text-[var(--text-primary)]">
              {channelHeaderLabel(channel)}
            </h4>
          </div>
          <Funnel stages={channel.stages} printMode={printMode} />
        </section>
      ))}
    </div>
  );
}
