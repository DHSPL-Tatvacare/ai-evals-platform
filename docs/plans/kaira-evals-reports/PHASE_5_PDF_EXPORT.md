# Phase 5 — PDF Export

## Objective

Build the professional PDF exporter that captures the on-screen report into a downloadable document. Uses the existing jsPDF + jsPDF-autoTable infrastructure, extended with chart image capture from Recharts and the callout/card design system.

## Pre-flight

- Branch: `feat/report-phase-5-pdf` from `main` (Phase 4 merged)
- Primary file: `src/features/evalRuns/export/reportPdfExporter.ts`
- Deps already available: `jspdf@4.0.0`, `jspdf-autotable@5.0.7`, `recharts@3.7.0`
- Study existing: `src/services/export/exporters/pdfExporter.ts` (403 lines) for patterns

---

## Step 1: Chart Capture Utility

### Problem

Recharts renders to SVG in the DOM. jsPDF needs rasterized images (PNG). We need a bridge.

### Solution: Off-screen rendering + SVG→Canvas→PNG

```typescript
// src/features/evalRuns/export/chartCapture.ts

/**
 * Capture a Recharts chart as a PNG data URL.
 *
 * Strategy:
 * 1. The chart is already rendered on-screen in the Report tab
 * 2. Find the SVG element inside the chart container
 * 3. Serialize SVG → create Image → draw on Canvas → toDataURL
 *
 * This avoids off-screen rendering entirely — we capture what's already visible.
 */

export async function captureSvgAsImage(
  containerRef: HTMLElement,
  width: number,
  height: number,
): Promise<string> {
  const svg = containerRef.querySelector('svg');
  if (!svg) throw new Error('No SVG found in container');

  // Clone SVG with computed styles baked in
  const cloned = svg.cloneNode(true) as SVGElement;
  cloned.setAttribute('width', String(width));
  cloned.setAttribute('height', String(height));

  // Inline CSS variables (jsPDF can't resolve them)
  _inlineCssVariables(cloned);

  const svgData = new XMLSerializer().serializeToString(cloned);
  const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(svgBlob);

  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = width * 2;    // 2x for retina quality
      canvas.height = height * 2;
      const ctx = canvas.getContext('2d')!;
      ctx.scale(2, 2);
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0, width, height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL('image/png'));
    };
    img.onerror = reject;
    img.src = url;
  });
}

function _inlineCssVariables(element: SVGElement): void {
  // Walk all elements, resolve CSS var() references to actual values
  const all = element.querySelectorAll('*');
  const computed = getComputedStyle(document.documentElement);

  for (const el of all) {
    const style = (el as HTMLElement).style;
    if (!style) continue;
    for (let i = 0; i < style.length; i++) {
      const prop = style[i];
      const val = style.getPropertyValue(prop);
      if (val.includes('var(')) {
        const resolved = val.replace(/var\(--([^)]+)\)/g, (_, name) => {
          return computed.getPropertyValue(`--${name}`).trim() || '#000';
        });
        style.setProperty(prop, resolved);
      }
    }
  }
}
```

### Usage pattern in ReportTab:
```typescript
// Each chart section exposes a ref to its container
const correctnessChartRef = useRef<HTMLDivElement>(null);
const efficiencyChartRef = useRef<HTMLDivElement>(null);
// ...etc

// Capture all charts before PDF generation
const chartImages = await captureAllCharts({
  correctness: correctnessChartRef.current,
  efficiency: efficiencyChartRef.current,
  intentHistogram: intentChartRef.current,
  frictionCause: frictionCauseRef.current,
  recoveryQuality: recoveryQualityRef.current,
  avgTurns: avgTurnsRef.current,
  adversarial: adversarialChartRef.current,  // may be null
});
```

### Chart refs integration:
Each chart component (VerdictDistributions, FrictionAnalysis, etc.) wraps its Recharts in a `<div ref={chartRef}>`. The parent ReportTab passes refs down and collects them for capture.

Alternatively, use `forwardRef` on chart components, but passing explicit refs is simpler and more explicit.

---

## Step 2: PDF Layout Engine

### `src/features/evalRuns/export/reportPdfExporter.ts`

This is the largest file in the export system. Structure it as a class with clear page methods.

```typescript
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { ReportPayload } from '@/types/reports';

// --- Design Constants ---

const COLORS = {
  primary: [30, 41, 59],       // #1E293B slate-800
  accent: [59, 130, 246],      // #3B82F6 blue-500
  success: [16, 185, 129],     // #10B981
  warning: [245, 158, 11],     // #F59E0B
  danger: [239, 68, 68],       // #EF4444
  muted: [148, 163, 184],      // #94A3B8
  surface: [248, 250, 252],    // #F8FAFC
  surfaceAlt: [241, 245, 249], // #F1F5F9
  white: [255, 255, 255],
  criticalDark: [153, 27, 27], // #991B1B
  violet: [139, 92, 246],      // #8B5CF6
  sky: [14, 165, 233],         // #0EA5E9
} as const;

const MARGINS = { left: 20, right: 20, top: 18, bottom: 22 };
const CONTENT_WIDTH = 170; // A4 width (210) - left (20) - right (20)
const PAGE_HEIGHT = 297;

const FONTS = {
  title: 18,
  sectionTitle: 14,
  body: 10,
  small: 9,
  tiny: 8,
};

// --- Types ---

interface ChartImages {
  correctness?: string;   // data:image/png;base64,...
  efficiency?: string;
  intentHistogram?: string;
  frictionCause?: string;
  recoveryQuality?: string;
  avgTurns?: string;
  adversarial?: string;
  customEvals?: Record<string, string>;
}

// --- Exporter Class ---

export class ReportPdfExporter {
  private doc: jsPDF;
  private report: ReportPayload;
  private charts: ChartImages;
  private currentY: number = MARGINS.top;

  constructor(report: ReportPayload, charts: ChartImages) {
    this.doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    this.report = report;
    this.charts = charts;
  }

  async generate(): Promise<Blob> {
    this._renderCover();
    this._renderExecutiveSummary();
    this._renderVerdictDistributions();
    this._renderRuleCompliance();
    this._renderFrictionAnalysis();
    if (this.report.adversarial) {
      this._renderAdversarialBreakdown();
    }
    this._renderExemplarThreads();
    this._renderPromptGapAnalysis();
    this._renderRecommendations();

    return this.doc.output('blob');
  }

  // --- Page helpers ---

  private _ensureSpace(needed: number): void {
    if (this.currentY + needed > PAGE_HEIGHT - MARGINS.bottom) {
      this._addPage();
    }
  }

  private _addPage(): void {
    this.doc.addPage();
    this.currentY = MARGINS.top;
    this._renderPageHeader();
  }

  private _renderPageHeader(): void {
    const pageNum = this.doc.getNumberOfPages();
    this.doc.setFontSize(FONTS.tiny);
    this.doc.setTextColor(...COLORS.muted);
    this.doc.text(
      `Kaira Bot Evaluation Report · ${this.report.metadata.createdAt}`,
      MARGINS.left, 12
    );
    this.doc.text(`Page ${pageNum}`, 210 - MARGINS.right, 12, { align: 'right' });
    this.doc.setDrawColor(...COLORS.muted);
    this.doc.line(MARGINS.left, 14, 210 - MARGINS.right, 14);
  }

  private _renderFooter(): void {
    const pageCount = this.doc.getNumberOfPages();
    for (let i = 2; i <= pageCount; i++) {
      this.doc.setPage(i);
      this.doc.setFontSize(FONTS.tiny);
      this.doc.setTextColor(...COLORS.muted);
      this.doc.text(
        'AI Evals Platform · Confidential',
        MARGINS.left, PAGE_HEIGHT - 10
      );
      this.doc.text(
        `Page ${i}`,
        210 - MARGINS.right, PAGE_HEIGHT - 10,
        { align: 'right' }
      );
    }
  }

  // --- Section renderers (one per page/section) ---

  private _renderCover(): void { /* Page 1 — see spec below */ }
  private _renderExecutiveSummary(): void { /* Page 2 */ }
  private _renderVerdictDistributions(): void { /* Page 3 */ }
  private _renderRuleCompliance(): void { /* Page 4 */ }
  private _renderFrictionAnalysis(): void { /* Page 5 */ }
  private _renderAdversarialBreakdown(): void { /* Page 6 (conditional) */ }
  private _renderExemplarThreads(): void { /* Pages 7-8 */ }
  private _renderPromptGapAnalysis(): void { /* Page 9 */ }
  private _renderRecommendations(): void { /* Page 10 */ }
}
```

---

## Step 3: Page Implementations

### Cover Page

```
Elements:
  1. Gradient bar (draw colored rect across top)
  2. Title: "KAIRA BOT EVALUATION REPORT" (24pt, bold, centered)
  3. Health score donut (draw arc + center text)
  4. Metadata table (run name, date, model, data, scope, time)
  5. Footer: "Generated by AI Evals Platform · Tatvacare"

Health score donut implementation:
  - Draw outer arc using doc.ellipse() or canvas-based rendering
  - Simpler alternative: draw a filled circle segment
  - Center text: grade letter (24pt) + numeric (12pt)
  - Color: based on grade threshold (METRIC_COLOR equivalent)

Alternative (simpler, still professional):
  - Skip donut, use a large colored badge:
    Filled rounded rect with grade letter + score
    e.g., [  B+  78.2  ] in blue fill with white text
```

### Executive Summary

```
Elements:
  1. 4 metric boxes (draw rounded rects, add text)
  2. AI assessment (draw callout box with left border)
  3. Top issues (draw callout boxes with priority badges)

Metric boxes implementation:
  - 4 boxes, each ~40mm wide, 30mm tall
  - Rounded rect: doc.roundedRect(x, y, w, h, rx, ry, 'F')
  - Fill: COLORS.surface
  - Border: COLORS.surfaceAlt
  - Label: tiny, muted, centered
  - Value: 20pt, colored by threshold, centered
  - Progress bar: thin rect (1.5mm tall) with colored fill

Callout box implementation:
  - Left border: doc.setFillColor(...color); doc.rect(x, y, 2, height, 'F')
  - Background: doc.setFillColor(...bgColor); doc.roundedRect(x+2, y, w-2, h, 2, 2, 'F')
  - Text: doc.text(content, x+6, y+lineHeight)
  - Word-wrap: use doc.splitTextToSize(text, maxWidth) for all multi-line text
```

### Rule Compliance Table

```
Use jsPDF-autoTable for the structured table:

autoTable(this.doc, {
  startY: this.currentY,
  head: [['Rule', 'Section', 'Pass', 'Fail', 'Rate', 'Severity']],
  body: rules.map(r => [
    r.ruleId,
    r.section,
    String(r.passed),
    String(r.failed),
    `${(r.rate * 100).toFixed(0)}%`,
    r.severity,
  ]),
  theme: 'grid',
  headStyles: {
    fillColor: COLORS.primary,
    textColor: COLORS.white,
    fontSize: FONTS.small,
    fontStyle: 'bold',
  },
  bodyStyles: {
    fontSize: FONTS.small,
    textColor: COLORS.primary,
  },
  alternateRowStyles: {
    fillColor: COLORS.surface,
  },
  columnStyles: {
    0: { cellWidth: 50 },
    4: { halign: 'right' },
    5: { halign: 'center' },
  },
  didParseCell: (data) => {
    // Color the Rate column by threshold
    if (data.column.index === 4 && data.section === 'body') {
      const rate = parseFloat(data.cell.raw as string);
      if (rate < 60) data.cell.styles.textColor = COLORS.danger;
      else if (rate < 80) data.cell.styles.textColor = COLORS.warning;
      else data.cell.styles.textColor = COLORS.success;
    }
    // Color severity badges
    if (data.column.index === 5 && data.section === 'body') {
      const sev = data.cell.raw as string;
      if (sev === 'CRITICAL') data.cell.styles.textColor = COLORS.criticalDark;
      else if (sev === 'HIGH') data.cell.styles.textColor = COLORS.danger;
      else if (sev === 'MEDIUM') data.cell.styles.textColor = COLORS.warning;
    }
  },
  margin: { left: MARGINS.left, right: MARGINS.right },
});

this.currentY = (this.doc as any).lastAutoTable.finalY + 8;
```

### Exemplar Threads

```
For each exemplar:
  1. Thread header bar (colored rect with thread ID + verdict badges)
  2. Transcript messages (alternating user/bot bubbles)
  3. AI analysis callout
  4. Rule violations list (bad examples only)

Transcript rendering:
  - USER: blue-50 bg rect, blue left border, monospace text
  - BOT: green-50 (good) or red-50 (bad) bg, colored border
  - Use doc.splitTextToSize() to word-wrap content
  - Truncate messages > 300 chars with "..." suffix
  - Max 6 messages per exemplar to control page length

Page breaks:
  - Before each exemplar, check if >= 60mm space remains
  - If not, add page break
  - This keeps each exemplar card intact (no split across pages)
```

### Charts in PDF

```
For each captured chart image:
  const imgData = this.charts.correctness;
  if (imgData) {
    this._ensureSpace(60);
    this.doc.addImage(imgData, 'PNG', x, this.currentY, chartWidth, chartHeight);
    this.currentY += chartHeight + 4;
  }

Chart sizing:
  - Full-width charts: 170mm × 50mm
  - Half-width (side by side): 82mm × 45mm
  - Small (pie charts): 60mm × 60mm
```

---

## Step 4: Export Button Integration

### In ReportTab.tsx:

```typescript
const handleExportPdf = async () => {
  if (!report) return;

  setExporting(true);
  try {
    // Capture all chart images from rendered components
    const charts = await captureAllCharts(chartRefs);

    // Generate PDF
    const exporter = new ReportPdfExporter(report, charts);
    const blob = await exporter.generate();

    // Download
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `kaira-eval-report-${report.metadata.runId.slice(0, 8)}.pdf`;
    a.click();
    URL.revokeObjectURL(url);

    notificationService.success('Report exported successfully');
  } catch (err) {
    notificationService.error('Failed to export PDF');
    logger.error('PDF export failed', err);
  } finally {
    setExporting(false);
  }
};

// Button in top bar of ReportTab:
<button
  onClick={handleExportPdf}
  disabled={exporting || !report}
  className={cn(
    'flex items-center gap-2 px-4 py-2 rounded-lg',
    'bg-[var(--accent-primary)] text-white',
    'hover:opacity-90 disabled:opacity-50'
  )}
>
  {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
  Export PDF
</button>
```

---

## Step 5: Text Wrapping & Overflow Prevention

Critical for professional quality — no text should overflow its container.

```typescript
/**
 * Render wrapped text within a bounded box.
 * Returns the Y position after the last line.
 */
private _renderWrappedText(
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  fontSize: number = FONTS.body,
  color: number[] = COLORS.primary,
  lineHeight: number = 1.4,
): number {
  this.doc.setFontSize(fontSize);
  this.doc.setTextColor(...(color as [number, number, number]));
  const lines = this.doc.splitTextToSize(text, maxWidth);

  for (const line of lines) {
    this._ensureSpace(fontSize * lineHeight * 0.35);
    this.doc.text(line, x, y);
    y += fontSize * lineHeight * 0.35;
  }

  return y;
}

/**
 * Render a callout box (colored left border + tinted background + wrapped text).
 */
private _renderCalloutBox(
  text: string,
  variant: 'info' | 'success' | 'warning' | 'danger' | 'insight' | 'suggest',
  x: number,
  y: number,
  width: number,
  title?: string,
): number {
  const variantMap = {
    info:    { border: COLORS.sky,     bg: [240, 249, 255] },
    success: { border: COLORS.success, bg: [240, 253, 244] },
    warning: { border: COLORS.warning, bg: [255, 251, 235] },
    danger:  { border: COLORS.danger,  bg: [254, 242, 242] },
    insight: { border: COLORS.accent,  bg: [239, 246, 255] },
    suggest: { border: COLORS.violet,  bg: [245, 243, 255] },
  };

  const v = variantMap[variant];
  const padding = 4;
  const textWidth = width - padding * 2 - 3; // 3mm for left border

  // Calculate required height
  this.doc.setFontSize(FONTS.body);
  const titleLines = title ? this.doc.splitTextToSize(title, textWidth) : [];
  const bodyLines = this.doc.splitTextToSize(text, textWidth);
  const totalLines = titleLines.length + bodyLines.length;
  const boxHeight = (totalLines * FONTS.body * 0.5) + padding * 2;

  this._ensureSpace(boxHeight + 4);

  // Background
  this.doc.setFillColor(...(v.bg as [number, number, number]));
  this.doc.roundedRect(x, y, width, boxHeight, 1, 1, 'F');

  // Left border
  this.doc.setFillColor(...(v.border as [number, number, number]));
  this.doc.rect(x, y, 2, boxHeight, 'F');

  // Title
  let textY = y + padding + 3;
  if (title) {
    this.doc.setFontSize(FONTS.body);
    this.doc.setFont('helvetica', 'bold');
    this.doc.setTextColor(...COLORS.primary);
    for (const line of titleLines) {
      this.doc.text(line, x + 5, textY);
      textY += FONTS.body * 0.5;
    }
    this.doc.setFont('helvetica', 'normal');
  }

  // Body
  this.doc.setFontSize(FONTS.body);
  this.doc.setTextColor(51, 65, 85); // slate-700
  for (const line of bodyLines) {
    this.doc.text(line, x + 5, textY);
    textY += FONTS.body * 0.5;
  }

  return y + boxHeight + 4;
}
```

---

## Step 6: Font Handling

jsPDF ships with limited fonts (Helvetica, Times, Courier). For professional quality:

**Option A (recommended — keep it simple):**
- Use Helvetica (sans-serif) for body text — it's built-in and professional
- Use Courier for monospace (thread IDs, transcripts)
- This avoids font embedding complexity

**Option B (if design demands Inter):**
- Download Inter font as .ttf
- Convert to base64 with jsPDF font converter
- Register: `doc.addFont(interBase64, 'Inter', 'normal')`
- Increases PDF size by ~200KB
- Only pursue if Helvetica output looks insufficient

**Start with Option A. Upgrade to B only if the output isn't professional enough.**

---

## Verification Checklist

- [ ] PDF generates without errors for a real completed run
- [ ] Cover page: health score, metadata, branding all render correctly
- [ ] Executive summary: metric cards, AI narrative, top issues render
- [ ] Charts: all Recharts SVGs captured as clear PNG images in PDF
- [ ] Charts: no CSS variable artifacts (all resolved before capture)
- [ ] Rule compliance table: alternating rows, colored rates, severity badges
- [ ] Exemplar threads: transcripts wrap correctly, no overflow
- [ ] Callout boxes: colored borders, tinted backgrounds, proper text wrap
- [ ] Page breaks: no content split mid-element (cards, tables stay intact)
- [ ] Page headers and footers on every page (except cover)
- [ ] PDF file size < 2MB for a typical 20-thread run
- [ ] PDF filename: `kaira-eval-report-{runId-prefix}.pdf`
- [ ] Download works on Chrome, Firefox, Safari
- [ ] "Export PDF" button shows loading spinner during generation
- [ ] Error notification if PDF generation fails

## Known Limitations (acceptable for v1)

- Font: Helvetica only (no Inter). Professional enough for v1.
- Charts: Rasterized at 2x DPI. Good quality but not vector.
- Custom eval charts: only if those chart refs are captured. May need to be added case-by-case.
- Very long transcripts (>10 messages) are truncated to keep PDF size manageable.
