import type { ComposedReport } from '@/features/reportBuilder/types';

export type ChatProvider = 'gemini' | 'openai';

export interface ToolCallDetailData {
  executionMs: number;
  sqlUsed?: string | null;
  rowCount?: number | null;
  cacheHit?: boolean | null;
  error?: string | null;
}

export interface ToolCallBadgeData {
  name: string;
  summary?: string;
  detail?: ToolCallDetailData | null;
  status: 'running' | 'done' | 'failed';
}

export interface SeriesConfig {
  dataKey: string;
  type: 'bar' | 'line' | 'area' | 'scatter';
  stackId?: string;
}

export interface ChartSpec {
  type: string;
  title: string;
  xKey: string;
  yKey?: string;
  seriesKeys: string[];
  series?: SeriesConfig[];
  xLabel: string;
  yLabel: string;
  legendPosition?: 'top' | 'bottom' | 'right' | 'none';
  alternatives?: string[];
}

export interface ChartData {
  spec: ChartSpec;
  data: Record<string, unknown>[];
  sqlQuery: string;
  sourceQuestion: string;
}

export interface WidgetMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls: ToolCallBadgeData[];
  composedReport?: ComposedReport | null;
  chart?: ChartData;
  status: 'complete' | 'streaming' | 'error';
}

export interface ChatDefaults {
  gemini: { model: string };
  openai: { model: string };
}

export interface BuilderSessionData {
  sessionId: string;
  provider: ChatProvider;
  model: string;
}

export interface PromptTemplate {
  label: string;
  prompt: string;
  category?: string;
}

export interface ChatWidgetConfig {
  enabled?: boolean;
  promptTemplates?: PromptTemplate[];
  capabilities?: string[];
}

export type WidgetView = 'chat' | 'history';

export interface WidgetSessionSummary {
  id: string;
  title: string;
  updatedAt: Date;
  status: string;
}
