/**
 * Universal PDF Exporter
 *
 * Renders a formatted report from EvalExportPayload. Completely app-agnostic —
 * section structure adapts to whatever evaluations are present.
 */
import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { Exporter, EvalExportPayload, EvalExportEntry } from '../types';

// jsPDF + autoTable type augmentation
type DocWithAutoTable = jsPDF & { lastAutoTable: { finalY: number } };

// Color constants
const COLORS = {
  title: [44, 62, 80] as [number, number, number],
  subtitle: [52, 73, 94] as [number, number, number],
  black: [0, 0, 0] as [number, number, number],
  gray: [128, 128, 128] as [number, number, number],
  divider: [200, 200, 200] as [number, number, number],
  headerBg: [44, 62, 80] as [number, number, number],
  success: [40, 167, 69] as [number, number, number],
  warning: [255, 193, 7] as [number, number, number],
  danger: [220, 53, 69] as [number, number, number],
};

export const pdfExporter: Exporter = {
  id: 'pdf',
  name: 'PDF (Evaluation Report)',
  extension: 'pdf',
  mimeType: 'application/pdf',

  async export(data: EvalExportPayload): Promise<Blob> {
    const doc = new jsPDF();
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const margin = 20;
    const contentWidth = pageWidth - 2 * margin;
    let currentPage = 1;

    // ── Page helpers ──

    const addFooter = () => {
      doc.setFontSize(8);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(...COLORS.gray);
      doc.text(`Page ${currentPage}`, pageWidth / 2, pageHeight - 10, { align: 'center' });
      doc.text(
        `Generated: ${data.exportedAt.toLocaleString()}`,
        pageWidth - margin, pageHeight - 10, { align: 'right' },
      );
      doc.setTextColor(...COLORS.black);
    };

    const addNewPage = () => {
      addFooter();
      doc.addPage();
      currentPage++;
    };

    const drawDivider = (y: number) => {
      doc.setDrawColor(...COLORS.divider);
      doc.setLineWidth(0.5);
      doc.line(margin, y, pageWidth - margin, y);
    };

    const ensureSpace = (needed: number, y: number): number => {
      if (y + needed > pageHeight - 30) {
        addNewPage();
        return 20;
      }
      return y;
    };

    const sectionTitle = (text: string, y: number): number => {
      y = ensureSpace(20, y);
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(...COLORS.black);
      doc.text(text, margin, y);
      return y + 8;
    };

    const getAutoTableY = (): number => {
      return (doc as DocWithAutoTable).lastAutoTable.finalY;
    };

    // ═══════════════════════════════════════════════════════════
    // COVER
    // ═══════════════════════════════════════════════════════════
    let y = 40;

    doc.setFontSize(22);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...COLORS.title);
    doc.text(`${data.source.appLabel} Evaluation Report`, pageWidth / 2, y, { align: 'center' });
    y += 12;

    doc.setFontSize(14);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...COLORS.subtitle);
    doc.text(data.source.title, pageWidth / 2, y, { align: 'center' });
    y += 20;

    drawDivider(y);
    y += 12;

    // ═══════════════════════════════════════════════════════════
    // SOURCE METADATA
    // ═══════════════════════════════════════════════════════════
    y = sectionTitle('Source Details', y);

    const metaRows: string[][] = [
      ['Created', data.source.createdAt],
    ];
    for (const [key, value] of Object.entries(data.source.metadata)) {
      metaRows.push([formatMetaKey(key), String(value ?? '')]);
    }

    autoTable(doc, {
      startY: y,
      head: [],
      body: metaRows,
      theme: 'plain',
      styles: { fontSize: 10, cellPadding: 3 },
      columnStyles: {
        0: { fontStyle: 'bold', cellWidth: 45 },
        1: { cellWidth: contentWidth - 45 },
      },
      margin: { left: margin, right: margin },
    });
    y = getAutoTableY() + 12;

    // ═══════════════════════════════════════════════════════════
    // EVALUATOR RESULTS OVERVIEW
    // ═══════════════════════════════════════════════════════════
    if (data.evaluations.length > 0) {
      drawDivider(y);
      y += 10;
      y = sectionTitle('Evaluator Results Overview', y);

      const summaryHead = [['Name', 'Type', 'Status', 'Score', 'Model', 'Duration']];
      const summaryBody = data.evaluations.map(entry => [
        entry.evaluatorName,
        entry.evaluatorType,
        entry.status.toUpperCase(),
        formatPrimaryMetric(entry),
        entry.model ?? '-',
        formatDuration(entry.durationMs),
      ]);

      autoTable(doc, {
        startY: y,
        head: summaryHead,
        body: summaryBody,
        theme: 'striped',
        styles: { fontSize: 9, cellPadding: 2.5 },
        headStyles: { fillColor: COLORS.headerBg, textColor: 255, fontStyle: 'bold' },
        margin: { left: margin, right: margin },
      });
      y = getAutoTableY() + 12;
    }

    // ═══════════════════════════════════════════════════════════
    // PER-EVALUATOR SECTIONS
    // ═══════════════════════════════════════════════════════════
    for (const entry of data.evaluations) {
      const hasContent = entry.fields.length > 0
        || entry.detailColumns
        || entry.overallAssessment
        || entry.reasoning;

      if (!hasContent) continue;

      // Start new page per evaluator to keep sections clean
      addNewPage();
      y = 20;

      y = sectionTitle(entry.evaluatorName, y);

      // Score card
      if (entry.primaryMetric) {
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        doc.text(`${entry.primaryMetric.label}: `, margin, y);
        const labelWidth = doc.getTextWidth(`${entry.primaryMetric.label}: `);

        doc.setFont('helvetica', 'normal');
        const scoreColor = getScoreColor(entry);
        doc.setTextColor(...scoreColor);
        doc.text(formatPrimaryMetric(entry), margin + labelWidth, y);
        doc.setTextColor(...COLORS.black);
        y += 8;
      }

      // Status + model info
      doc.setFontSize(9);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(...COLORS.gray);
      const infoParts: string[] = [`Status: ${entry.status}`];
      if (entry.model) infoParts.push(`Model: ${entry.model}`);
      if (entry.durationMs) infoParts.push(`Duration: ${formatDuration(entry.durationMs)}`);
      doc.text(infoParts.join('  |  '), margin, y);
      doc.setTextColor(...COLORS.black);
      y += 10;

      // Fields table
      if (entry.fields.length > 0) {
        autoTable(doc, {
          startY: y,
          head: [['Field', 'Value']],
          body: entry.fields.map(f => [f.label, formatFieldValue(f.value)]),
          theme: 'plain',
          styles: { fontSize: 9, cellPadding: 2.5 },
          headStyles: { fillColor: COLORS.headerBg, textColor: 255, fontStyle: 'bold' },
          columnStyles: {
            0: { fontStyle: 'bold', cellWidth: 50 },
            1: { cellWidth: contentWidth - 50 },
          },
          margin: { left: margin, right: margin },
        });
        y = getAutoTableY() + 8;
      }

      // Overall assessment
      if (entry.overallAssessment) {
        y = ensureSpace(30, y);
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        doc.text('Overall Assessment:', margin, y);
        y += 5;

        doc.setFont('helvetica', 'normal');
        doc.setFontSize(9);
        const lines = doc.splitTextToSize(entry.overallAssessment, contentWidth);
        doc.text(lines, margin, y);
        y += lines.length * 4.5 + 8;
      }

      // Reasoning
      if (entry.reasoning) {
        y = ensureSpace(30, y);
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        doc.text('Reasoning:', margin, y);
        y += 5;

        doc.setFont('helvetica', 'normal');
        doc.setFontSize(9);
        const lines = doc.splitTextToSize(entry.reasoning, contentWidth);
        doc.text(lines, margin, y);
        y += lines.length * 4.5 + 8;
      }

      // Detail table (segments/fields/threads)
      if (entry.detailColumns && entry.detailRows?.length) {
        y = ensureSpace(40, y);
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        doc.text('Detailed Results', margin, y);
        y += 6;

        // Compute dynamic column widths based on column count
        const colCount = entry.detailColumns.length;
        const colWidth = contentWidth / colCount;
        const colStyles: Record<number, { cellWidth: number }> = {};
        for (let i = 0; i < colCount; i++) {
          colStyles[i] = { cellWidth: Math.min(colWidth, 45) };
        }

        autoTable(doc, {
          startY: y,
          head: [entry.detailColumns],
          body: entry.detailRows.map(r => r.map(cell => String(cell ?? ''))),
          theme: 'striped',
          styles: { fontSize: 7, cellPadding: 1.5, overflow: 'linebreak' },
          headStyles: { fillColor: COLORS.headerBg, textColor: 255, fontStyle: 'bold', fontSize: 7 },
          margin: { left: margin, right: margin },
          didDrawPage: () => { currentPage++; },
        });
        y = getAutoTableY() + 10;
      }
    }

    // ═══════════════════════════════════════════════════════════
    // HUMAN REVIEW CORRECTIONS
    // ═══════════════════════════════════════════════════════════
    const reviewEntries = data.evaluations.filter(e => e.humanReview);
    if (reviewEntries.length > 0) {
      addNewPage();
      y = 20;

      y = sectionTitle('Human Review Corrections', y);

      for (const entry of reviewEntries) {
        const hr = entry.humanReview!;

        // Verdict + stats
        const hrData: string[][] = [
          ['Verdict', hr.verdict.toUpperCase()],
          ['Stats', `Total: ${hr.stats.total} | Accepted: ${hr.stats.accepted} | Rejected: ${hr.stats.rejected} | Corrected: ${hr.stats.corrected}`],
        ];
        if (hr.notes) {
          hrData.push(['Notes', hr.notes]);
        }

        autoTable(doc, {
          startY: y,
          head: [],
          body: hrData,
          theme: 'plain',
          styles: { fontSize: 9, cellPadding: 3 },
          columnStyles: {
            0: { fontStyle: 'bold', cellWidth: 30 },
            1: { cellWidth: contentWidth - 30 },
          },
          margin: { left: margin, right: margin },
        });
        y = getAutoTableY() + 8;

        // Corrections table
        const corrected = hr.items.filter(i => i.correctedValue || i.verdict === 'correct');
        if (corrected.length > 0) {
          autoTable(doc, {
            startY: y,
            head: [['#', 'Index', 'Verdict', 'Corrected Value', 'Comment']],
            body: corrected.map((item, i) => [
              String(i + 1),
              String(item.index + 1),
              item.verdict,
              item.correctedValue ?? '-',
              item.comment ?? '-',
            ]),
            theme: 'striped',
            styles: { fontSize: 8, cellPadding: 2, overflow: 'linebreak' },
            headStyles: { fillColor: COLORS.headerBg, textColor: 255, fontStyle: 'bold' },
            margin: { left: margin, right: margin },
            didDrawPage: () => { currentPage++; },
          });
          y = getAutoTableY() + 10;
        }
      }
    }

    // Final footer
    addFooter();
    return doc.output('blob');
  },
};

// ═══════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════

function formatPrimaryMetric(entry: EvalExportEntry): string {
  if (!entry.primaryMetric) return '-';
  const { value, format } = entry.primaryMetric;
  if (format === 'percentage') return `${value}%`;
  if (format === 'boolean') return value ? 'Yes' : 'No';
  if (format === 'verdict') return String(value ?? '').toUpperCase();
  return String(value ?? '-');
}

function formatDuration(ms?: number): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatFieldValue(v: unknown): string {
  if (v == null) return '-';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function formatMetaKey(key: string): string {
  return key
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, s => s.toUpperCase())
    .replace(/_/g, ' ');
}

function getScoreColor(entry: EvalExportEntry): [number, number, number] {
  if (!entry.primaryMetric) return COLORS.black;
  const { value, format } = entry.primaryMetric;

  if (format === 'percentage' || format === 'number') {
    const num = Number(value);
    if (isNaN(num)) return COLORS.black;
    if (num >= 80) return COLORS.success;
    if (num >= 50) return COLORS.warning;
    return COLORS.danger;
  }
  if (format === 'verdict') {
    const v = String(value).toLowerCase();
    if (v.includes('accept')) return COLORS.success;
    if (v.includes('reject')) return COLORS.danger;
    return COLORS.warning;
  }
  return COLORS.black;
}
