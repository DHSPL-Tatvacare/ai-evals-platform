/**
 * Universal CSV Exporter
 *
 * Multi-section CSV structure that works cleanly in Excel/Sheets.
 * Completely app-agnostic — driven entirely by EvalExportPayload.
 */
import type { Exporter, EvalExportPayload, EvalExportEntry, ExportField } from '../types';

const UTF8_BOM = '\uFEFF';

function escapeCSV(value: unknown): string {
  if (value == null) return '';
  const str = String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function formatDuration(ms?: number): string {
  if (ms == null) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatPrimaryMetric(entry: EvalExportEntry): string {
  if (!entry.primaryMetric) return '';
  const { value, format } = entry.primaryMetric;
  if (format === 'percentage') return `${value}%`;
  if (format === 'boolean') return value ? 'Yes' : 'No';
  return String(value ?? '');
}

function row(cells: unknown[]): string {
  return cells.map(escapeCSV).join(',');
}

export const csvExporter: Exporter = {
  id: 'csv',
  name: 'CSV (Evaluation Report)',
  extension: 'csv',
  mimeType: 'text/csv;charset=utf-8',

  async export(data: EvalExportPayload): Promise<Blob> {
    const lines: string[] = [];

    // ── Section 1: Header ──
    lines.push(row(['EVALUATION REPORT']));
    lines.push(row(['Source', data.source.title]));
    lines.push(row(['App', data.source.appLabel]));
    lines.push(row(['Exported', data.exportedAt.toLocaleString()]));
    lines.push(row(['Created', data.source.createdAt]));

    // Metadata
    for (const [key, value] of Object.entries(data.source.metadata)) {
      lines.push(row([key, value]));
    }
    lines.push('');

    // ── Section 2: Evaluator Results Summary ──
    if (data.evaluations.length > 0) {
      lines.push(row(['EVALUATOR RESULTS']));
      lines.push(row(['Name', 'Type', 'Status', 'Score', 'Model', 'Duration', 'Completed']));

      for (const entry of data.evaluations) {
        lines.push(row([
          entry.evaluatorName,
          entry.evaluatorType,
          entry.status,
          formatPrimaryMetric(entry),
          entry.model ?? '',
          formatDuration(entry.durationMs),
          entry.completedAt ?? '',
        ]));
      }
      lines.push('');
    }

    // ── Section 3+: Per-evaluator detail ──
    for (const entry of data.evaluations) {
      const hasFields = entry.fields.length > 0;
      const hasDetail = entry.detailColumns && entry.detailRows?.length;
      const hasAssessment = !!entry.overallAssessment;
      const hasReasoning = !!entry.reasoning;

      if (!hasFields && !hasDetail && !hasAssessment && !hasReasoning) continue;

      lines.push(row([`EVALUATOR: ${entry.evaluatorName} — Details`]));

      // Fields table
      if (hasFields) {
        lines.push(row(['Field', 'Value', 'Type', 'Role']));
        for (const field of entry.fields) {
          lines.push(row([
            field.label,
            formatFieldValue(field),
            field.type,
            field.role ?? '',
          ]));
        }
      }

      // Overall assessment
      if (hasAssessment) {
        lines.push('');
        lines.push(row(['Overall Assessment']));
        lines.push(row([entry.overallAssessment]));
      }

      // Reasoning
      if (hasReasoning) {
        lines.push('');
        lines.push(row(['Reasoning']));
        lines.push(row([entry.reasoning]));
      }

      // Detail table (segments, fields, threads)
      if (hasDetail) {
        lines.push('');
        lines.push(row(entry.detailColumns!));
        for (const detailRow of entry.detailRows!) {
          lines.push(row(detailRow));
        }
      }

      lines.push('');
    }

    // ── Final Section: Human Review Corrections ──
    const reviewEntries = data.evaluations.filter(e => e.humanReview);
    if (reviewEntries.length > 0) {
      for (const entry of reviewEntries) {
        const hr = entry.humanReview!;
        lines.push(row([`HUMAN REVIEW CORRECTIONS (${entry.evaluatorName})`]));
        lines.push(row(['Verdict', hr.verdict]));
        lines.push(row(['Notes', hr.notes]));
        lines.push(row([
          'Stats',
          `Total: ${hr.stats.total}, Accepted: ${hr.stats.accepted}, Rejected: ${hr.stats.rejected}, Corrected: ${hr.stats.corrected}`,
        ]));
        lines.push('');

        if (hr.items.length > 0) {
          lines.push(row(['#', 'Index', 'Verdict', 'Corrected Value', 'Comment']));
          hr.items.forEach((item, i) => {
            lines.push(row([
              i + 1,
              item.index + 1,
              item.verdict,
              item.correctedValue ?? '',
              item.comment ?? '',
            ]));
          });
          lines.push('');
        }
      }
    }

    const csvContent = UTF8_BOM + lines.join('\r\n');
    return new Blob([csvContent], { type: this.mimeType });
  },
};

function formatFieldValue(field: ExportField): string {
  const v = field.value;
  if (v == null) return '';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}
