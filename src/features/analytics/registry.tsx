import type { ReactNode } from 'react';
import type { AppId } from '@/types';
import type { ReportPayload } from '@/types/reports';
import type { InsideSalesReportPayload } from '@/types/insideSalesReport';
import { KairaReportView } from '@/features/evalRuns/components/report/KairaReportView';
import { InsideSalesReportView } from '@/features/insideSales/components/report/InsideSalesReportView';
import { KairaCrossRunDashboard } from './KairaCrossRunDashboard';
import { InsideSalesCrossRunDashboard } from './InsideSalesCrossRunDashboard';

interface ReportConfig<TReport = unknown> {
  supportsPdf: boolean;
  render: (report: TReport, context: { runId: string; appId: AppId; actions: ReactNode }) => ReactNode;
}

interface CrossRunConfig {
  supportsCrossRun: boolean;
  render: (appId: AppId) => ReactNode;
}

export interface AnalyticsAppConfig<TReport = unknown> {
  report?: ReportConfig<TReport>;
  crossRun?: CrossRunConfig;
}

const disabledConfig: AnalyticsAppConfig = {};

const analyticsRegistry: Partial<Record<AppId, AnalyticsAppConfig>> = {
  'voice-rx': disabledConfig,
  'kaira-bot': {
    report: {
      supportsPdf: true,
      render: (report, context) => (
        <KairaReportView report={report as ReportPayload} runId={context.runId} actions={context.actions} />
      ),
    },
    crossRun: {
      supportsCrossRun: true,
      render: (appId) => <KairaCrossRunDashboard appId={appId} />,
    },
  },
  'inside-sales': {
    report: {
      supportsPdf: true,
      render: (report, context) => <InsideSalesReportView report={report as InsideSalesReportPayload} actions={context.actions} />,
    },
    crossRun: {
      supportsCrossRun: true,
      render: (appId) => <InsideSalesCrossRunDashboard appId={appId} />,
    },
  },
};

export function getAnalyticsConfig(appId: AppId): AnalyticsAppConfig {
  return analyticsRegistry[appId] ?? disabledConfig;
}
