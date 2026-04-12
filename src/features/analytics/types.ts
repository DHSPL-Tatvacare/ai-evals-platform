export interface SavedChart {
  id: string;
  appId: string;
  title: string;
  description: string;
  sqlQuery: string;
  chartConfig: {
    type: 'bar' | 'horizontal_bar' | 'line' | 'pie' | 'stacked_bar';
    xKey: string;
    yKey?: string;
    seriesKeys: string[];
    xLabel: string;
    yLabel: string;
  };
  sourceQuestion?: string;
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
