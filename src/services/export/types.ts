import type { EvalType } from '@/types';

// ═══════════════════════════════════════════════════════════════
// Universal Export Payload — app-agnostic data contract
// ═══════════════════════════════════════════════════════════════

export interface EvalExportPayload {
  exportedAt: Date;
  source: ExportSource;
  evaluations: EvalExportEntry[];
}

export interface ExportSource {
  id: string;
  appId: string;
  appLabel: string;
  title: string;
  type: 'listing' | 'session';
  createdAt: string;
  metadata: Record<string, unknown>;
}

export interface EvalExportEntry {
  runId: string;
  evaluatorName: string;
  evaluatorType: 'built-in' | 'custom' | 'human';
  evalType: EvalType;
  status: string;
  model?: string;
  completedAt?: string;
  durationMs?: number;

  /** Primary metric (the "score" shown in cards) */
  primaryMetric?: {
    key: string;
    label: string;
    value: unknown;
    format: 'verdict' | 'percentage' | 'number' | 'boolean' | 'text';
  };

  /** All output fields (custom eval schema fields, or built-in statistics) */
  fields: ExportField[];

  /** Narrative */
  reasoning?: string;
  overallAssessment?: string;

  /** Row-level detail (segments/fields/threads) */
  detailColumns?: string[];
  detailRows?: unknown[][];

  /** Linked human review corrections */
  humanReview?: ExportHumanReview;
}

export interface ExportField {
  key: string;
  label: string;
  value: unknown;
  type: string;
  role?: 'metric' | 'reasoning' | 'detail';
}

export interface ExportHumanReview {
  verdict: string;
  notes: string;
  stats: { total: number; accepted: number; rejected: number; corrected: number };
  items: Array<{
    index: number;
    verdict: string;
    correctedValue?: string;
    comment?: string;
  }>;
}

// ═══════════════════════════════════════════════════════════════
// Exporter interface
// ═══════════════════════════════════════════════════════════════

export interface Exporter {
  id: string;
  name: string;
  extension: string;
  mimeType: string;
  export(data: EvalExportPayload): Promise<Blob>;
}
