import type {
  ChartPayloadChart,
  SeriesConfig,
} from '@/features/chat-widget/types';

export interface SavedChartRendererConfig {
  type: string;
  xKey: string;
  yKey?: string;
  seriesKeys?: string[];
  series?: SeriesConfig[];
  xLabel?: string;
  yLabel?: string;
  legendPosition?: 'top' | 'bottom' | 'right' | 'none';
  title?: string;
  colorMap?: Record<string, string>;
}

/**
 * Phase 6 §741, §743 — the stored canonical is the ``kind`` + ``spec``
 * projection of the generated ``ChartPayloadChart``. The accompanying
 * ``data`` rows arrive separately from the chart-data route, so
 * replay-time validation runs on the assembled
 * ``{ kind, spec, data }`` triple via ``toValidatedChartPayload`` in
 * ``chartReplayValidation.ts`` — not on a bespoke local shape.
 */
export type SavedChartCanonicalConfig = Pick<ChartPayloadChart, 'kind' | 'spec'>;

export interface SavedChartConfig {
  canonical?: SavedChartCanonicalConfig | null;
  renderer: SavedChartRendererConfig;
}

export interface SavedChart {
  id: string;
  appId: string;
  title: string;
  description: string;
  sqlQuery: string;
  chartConfig: SavedChartConfig;
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
  isPlatform: boolean;
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
    chartConfig?: SavedChartConfig;
    data?: Record<string, unknown>[];
    rowCount?: number;
    width: string;
    order: number;
    error?: string;
  }>;
}
