import { BarChart3 } from 'lucide-react';
import type { AppId } from '@/types';
import { useAppConfig } from '@/hooks';
import { EmptyState, PageSurface } from '@/components/ui';
import { usePageMetadata } from '@/config/pageMetadata';
import { PlatformCrossRunDashboard } from './components/PlatformReportRenderer';

interface Props {
  appId: AppId;
}

export function AnalyticsDashboardPage({ appId }: Props) {
  const appConfig = useAppConfig(appId);
  const { icon, title } = usePageMetadata('dashboard');

  if (!appConfig.analytics.capabilities.crossRunAnalytics) {
    return (
      <PageSurface icon={icon} title={title}>
        <EmptyState
          icon={BarChart3}
          title="Analytics not configured"
          description="This app does not have a cross-run analytics dashboard configured."
          className="w-full max-w-md"
          fill
        />
      </PageSurface>
    );
  }

  return <PlatformCrossRunDashboard appId={appId} />;
}
