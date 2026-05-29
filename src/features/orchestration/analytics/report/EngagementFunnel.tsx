import { FunnelCard, type FunnelStageDatum } from '@/components/ui';
import type { RunReportChannel } from '../types';

interface EngagementFunnelProps {
  channels: RunReportChannel[];
}

/** A single conversion funnel stitched left-to-right across every channel's
 *  stages, in channel order. Stage labels come from the API (`stages[].label`)
 *  so the funnel never hardcodes a vendor's stage names. */
export function EngagementFunnel({ channels }: EngagementFunnelProps) {
  const stages: FunnelStageDatum[] = channels.flatMap((channel) =>
    channel.stages.map((stage) => ({
      key: `${channel.capability}:${stage.key}`,
      label: stage.label,
      value: stage.count,
    })),
  );

  return <FunnelCard title="Engagement funnel" stages={stages} />;
}
