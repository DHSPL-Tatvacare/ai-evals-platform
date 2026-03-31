import { BarChart3 } from 'lucide-react';
import type { AppId } from '@/types';
import { EmptyState } from '@/components/ui';
import { getAnalyticsConfig } from './registry';

interface Props {
  appId: AppId;
}

export function AnalyticsDashboardPage({ appId }: Props) {
  const config = getAnalyticsConfig(appId);

  if (!config.crossRun?.supportsCrossRun) {
    return (
      <div className="flex flex-col flex-1 min-h-0">
        <div className="shrink-0 pb-4">
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">Dashboard</h1>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={BarChart3}
            title="Analytics not configured"
            description="This app does not have a cross-run analytics dashboard configured."
          />
        </div>
      </div>
    );
  }

  return <>{config.crossRun.render(appId)}</>;
}
