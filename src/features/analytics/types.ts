export interface SavedChart {
  id: string;
  appId: string;
  title: string;
  description: string;
  sqlQuery: string;
  chartConfig: {
    type: string;
    xKey: string;
    yKey?: string;
    seriesKeys?: string[];
    series?: import('@/features/chat-widget/types').SeriesConfig[];
    xLabel?: string;
    yLabel?: string;
    legendPosition?: 'top' | 'bottom' | 'right' | 'none';
  };
  sourceQuestion?: string;
  sourceSessionId?: string | null;
  visibility: 'private' | 'shared';
  createdAt: string;
  updatedAt: string;
}

export interface SavedDashboard {
  id: string;
  appId: string;
  title: string;
  description: string;
  chartEntries: Array<{ chartId: string; width: 'half' | 'full'; order: number }>;
  sourceSessionId?: string | null;
  visibility: 'private' | 'shared';
  createdAt: string;
  updatedAt: string;
}

export interface ChartDataResponse {
  data: Record<string, unknown>[];
  rowCount: number;
}

export interface DashboardDataResponse {
  dashboard: SavedDashboard;
  charts: Array<{
    chartId: string;
    title?: string;
    chartConfig?: SavedChart['chartConfig'];
    data?: Record<string, unknown>[];
    rowCount?: number;
    width: string;
    order: number;
    error?: string;
  }>;
}
