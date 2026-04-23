import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { analyticsLibraryForApp } from '@/config/routes';
import { useCurrentAppId } from '@/hooks';
import { cn } from '@/utils/cn';
import { analyticsLibraryApi } from '@/services/api/analyticsLibraryApi';
import { notificationService } from '@/services/notifications';
import { LoadingState, PageSurface } from '@/components/ui';
import { ActionIconButton } from '@/features/evalRuns/components/RunHeaderActions';
import { PAGE_METADATA } from '@/config/pageMetadata';
import { ChartRenderer } from './ChartRenderer';
import { deriveChartLayout } from '../chartLayout';
import { useMeasuredWidth } from '../useMeasuredWidth';
import { vegaLiteToRecharts } from '../vegaLiteToRecharts';
import type { DashboardDataResponse, SavedChart } from '../types';
import { toValidatedChartPayload } from '../chartReplayValidation';
import type { VegaLiteSpec } from '@/features/chat-widget/types';

type DashboardChartEntry = DashboardDataResponse['charts'][number];

function DashboardEntryChart({ entry }: { entry: DashboardChartEntry }) {
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  const config = entry.chartConfig as SavedChart['chartConfig'] | undefined;
  const rows = entry.data ?? [];
  if (!config) return null;

  const surface = entry.width === 'full' ? 'dashboard-full' : 'dashboard-half';
  const renderer = config.renderer;
  // Phase 6 §743: validate the stored canonical through the generated
  // validator before replay. Invalid payloads drop to the renderer
  // fallback rather than getting trusted on a shape check.
  let replayed = null as ReturnType<typeof vegaLiteToRecharts> | null;
  const validated = toValidatedChartPayload(config.canonical, rows);
  if (validated !== null) {
    try {
      replayed = vegaLiteToRecharts(validated.spec as unknown as VegaLiteSpec, validated.data);
    } catch {
      replayed = null;
    }
  }
  const type = replayed?.type ?? renderer.type;
  const layout = deriveChartLayout({
    surface,
    type,
    dataCount: rows.length,
    width,
  });

  return (
    <div ref={ref}>
      <ChartRenderer
        type={type}
        data={replayed?.data ?? rows}
        xKey={replayed?.xKey ?? renderer.xKey}
        yKey={replayed?.yKey ?? renderer.yKey}
        seriesKeys={replayed?.seriesKeys ?? renderer.seriesKeys}
        series={renderer.series}
        xLabel={replayed?.xLabel ?? renderer.xLabel}
        yLabel={replayed?.yLabel ?? renderer.yLabel}
        legendPosition={renderer.legendPosition ?? layout.legendPosition}
        yAxisWidthOverride={layout.yAxisWidth}
        marginOverride={layout.margin}
        tickFontSizeOverride={layout.tickFontSize}
        xTickCharCapOverride={layout.xTickCharCap}
        xTickIntervalOverride={layout.xTickInterval}
        height={layout.height}
      />
    </div>
  );
}

interface DashboardViewProps {
  dashboardId: string;
  onBack?: () => void;
}

export function DashboardView({ dashboardId }: DashboardViewProps) {
  const appId = useCurrentAppId();
  const [data, setData] = useState<DashboardDataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const back = { to: analyticsLibraryForApp(appId), label: 'Analytics' };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await analyticsLibraryApi.getDashboardData(dashboardId);
      setData(result);
    } catch {
      notificationService.error('Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }, [dashboardId]);

  useEffect(() => { void load(); }, [load]);

  if (loading || !data) {
    return (
      <PageSurface
        icon={PAGE_METADATA.analyticsDashboard.icon}
        title="Dashboard"
        back={back}
        showHeader={false}
      >
        <LoadingState message="Loading dashboard…" />
      </PageSurface>
    );
  }

  return (
    <PageSurface
      icon={PAGE_METADATA.analyticsDashboard.icon}
      title={data.dashboard.title}
      back={back}
      actions={
        <ActionIconButton
          icon={RefreshCw}
          label="Refresh"
          tooltip="Refresh"
          onClick={() => void load()}
          disabled={loading}
          spinning={loading}
        />
      }
    >
      <div className="flex-1 overflow-y-auto">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {data.charts
            .sort((a, b) => a.order - b.order)
            .map((entry) => (
              <div
                key={entry.chartId}
                className={cn(
                  'rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] p-4',
                  entry.width === 'full' && 'lg:col-span-2',
                )}
              >
                {entry.error ? (
                  <div className="text-xs text-[var(--color-verdict-fail)]">Error: {entry.error}</div>
                ) : (
                  <>
                    <h3 className="text-xs font-medium text-[var(--text-primary)] mb-2">{entry.title}</h3>
                     <DashboardEntryChart entry={entry} />
                   </>
                 )}
               </div>
            ))}
        </div>
      </div>
    </PageSurface>
  );
}
