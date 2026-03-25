# Phase 4 — Frontend Report Tab

## Objective

Build the on-screen "Report" tab in RunDetail that renders the full `ReportPayload` as an interactive, professional analysis view. This is the primary consumption surface — users review on-screen before exporting to PDF.

## Pre-flight

- Branch: `feat/report-phase-4-frontend` from `main` (Phase 3 merged)
- All components in: `src/features/evalRuns/components/report/`
- Reuse existing: `DistributionBar`, `VerdictBadge`, design tokens from `globals.css`
- Charts: Recharts (already in deps — `BarChart`, `PieChart`, `Cell`, `ResponsiveContainer`)
- Styling: Tailwind v4 + CSS variables, `cn()` for class merging

---

## Step 1: Shared UI Primitives (`src/features/evalRuns/components/report/shared/`)

These are reusable building blocks — used across all report sections AND in the PDF exporter.

### `CalloutBox.tsx`

```
Props:
  variant: 'info' | 'success' | 'warning' | 'danger' | 'insight' | 'suggest'
  title?: string
  children: ReactNode

Color map:
  info    → border: sky-500,    bg: sky-50,     icon: ℹ️
  success → border: emerald-500, bg: emerald-50, icon: ✓
  warning → border: amber-500,  bg: amber-50,   icon: ⚠
  danger  → border: red-500,    bg: red-50,     icon: ✗
  insight → border: blue-500,   bg: blue-50,    icon: 🔍 (or search icon)
  suggest → border: violet-500, bg: violet-50,  icon: 💡 (or lightbulb icon)

Rendered as:
  <div className={cn(
    'border-l-[3px] rounded-r-md px-4 py-3',
    variantStyles[variant]
  )}>
    {title && <div className="font-semibold text-sm mb-1">{title}</div>}
    <div className="text-sm leading-relaxed">{children}</div>
  </div>

IMPORTANT: Use Lucide icons (already in deps), not emoji. Map:
  info → Info icon, success → Check icon, warning → AlertTriangle,
  danger → XCircle, insight → Search, suggest → Lightbulb
```

### `SectionHeader.tsx`

```
Props:
  number: number
  title: string
  subtitle?: string

Rendered as:
  <div className="mb-6">
    <h2 className="text-lg font-bold text-[var(--text-primary)]">
      {number}. {title}
    </h2>
    {subtitle && <p className="text-sm text-[var(--text-secondary)] mt-1">{subtitle}</p>}
  </div>
```

### `MetricCard.tsx`

```
Props:
  label: string
  value: string | number
  suffix?: string       // "%" etc.
  color: string         // CSS color value
  weight?: string       // "25%" — shown as subtitle
  progressValue?: number // 0-100 for progress bar

Rendered as:
  <div className="bg-[var(--bg-secondary)] border border-[var(--border-primary)]
                  rounded-lg p-4 text-center">
    <div className="text-xs text-[var(--text-secondary)] uppercase tracking-wider mb-2">
      {label}
    </div>
    <div className="text-2xl font-bold" style={{ color }}>
      {value}{suffix}
    </div>
    {progressValue != null && (
      <div className="mt-3 h-1.5 bg-[var(--border-primary)] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${progressValue}%`, backgroundColor: color }} />
      </div>
    )}
    {weight && <div className="text-xs text-[var(--text-tertiary)] mt-2">Weight: {weight}</div>}
  </div>
```

### `PriorityBadge.tsx`

```
Props:
  priority: 'P0' | 'P1' | 'P2'

Color map:
  P0 → bg: red-100, text: red-800, label: "P0 · CRITICAL"
  P1 → bg: amber-100, text: amber-800, label: "P1 · HIGH"
  P2 → bg: blue-100, text: blue-800, label: "P2 · MEDIUM"
```

### Color utility (add to existing or create `src/features/evalRuns/components/report/shared/colors.ts`):

```typescript
export const METRIC_COLOR = (value: number): string => {
  if (value >= 80) return 'var(--color-success, #10B981)';
  if (value >= 60) return 'var(--color-warning, #F59E0B)';
  return 'var(--color-danger, #EF4444)';
};

export const VERDICT_COLORS: Record<string, string> = {
  // Correctness
  'PASS': '#10B981',
  'NOT APPLICABLE': '#94A3B8',
  'SOFT FAIL': '#F59E0B',
  'HARD FAIL': '#EF4444',
  'CRITICAL': '#991B1B',
  // Efficiency
  'EFFICIENT': '#10B981',
  'ACCEPTABLE': '#3B82F6',
  'INCOMPLETE': '#94A3B8',
  'FRICTION': '#F59E0B',
  'BROKEN': '#EF4444',
};

export const SEVERITY_COLORS: Record<string, string> = {
  'LOW': '#94A3B8',
  'MEDIUM': '#F59E0B',
  'HIGH': '#EF4444',
  'CRITICAL': '#991B1B',
  '—': '#94A3B8',
};
```

**Note:** Check if similar color maps already exist in `DistributionBar.tsx` or `VerdictBadge.tsx`. If so, extract to this shared location and update existing components to import from here. Avoid duplication.

---

## Step 2: Report Tab Container (`ReportTab.tsx`)

```
This is the top-level component added as a tab in RunDetail.

Props:
  runId: string
  run: EvalRun  // already loaded by RunDetail

State:
  report: ReportPayload | null
  loading: boolean
  error: string | null

Behavior:
  1. On mount → call reportsApi.fetchReport(runId)
  2. Show loading skeleton while fetching (use existing skeleton patterns)
  3. On success → render all sections in order
  4. On error → show error callout with retry button
  5. "Export PDF" button in top-right corner (Phase 5 wires this up)

Layout:
  <div className="space-y-8 max-w-[900px] mx-auto">
    <ReportHeader metadata={report.metadata} healthScore={report.healthScore} />
    <ExecutiveSummary
      healthScore={report.healthScore}
      narrative={report.narrative}
    />
    <VerdictDistributions distributions={report.distributions} />
    <RuleComplianceTable ruleCompliance={report.ruleCompliance} />
    <FrictionAnalysis friction={report.friction} />
    {report.adversarial && (
      <AdversarialBreakdown adversarial={report.adversarial} />
    )}
    <ExemplarThreads exemplars={report.exemplars} narrative={report.narrative} />
    <PromptGapAnalysis
      productionPrompts={report.productionPrompts}
      narrative={report.narrative}
    />
    <Recommendations narrative={report.narrative} />
  </div>

  Bottom: Disclaimer CalloutBox (info variant)
```

### Integration with RunDetail.tsx:

Add "Report" as a new tab. Only show for completed batch_thread runs:

```typescript
// In RunDetail.tsx tab definitions:
const tabs = [
  { id: 'threads', label: 'Threads', ... },
  { id: 'adversarial', label: 'Adversarial', ... },
  // NEW:
  ...(run.status === 'completed' || run.status === 'completed_with_errors'
    ? [{ id: 'report', label: 'Report' }]
    : []),
];

// In tab content rendering:
{activeTab === 'report' && (
  <ReportTab runId={runId} run={run} />
)}
```

### Lazy loading:
- The Report tab fetches its own data on mount (not pre-loaded by RunDetail)
- This keeps RunDetail fast — report data is only loaded when the user clicks the tab
- ReportTab manages its own loading/error state

---

## Step 3: Executive Summary (`ExecutiveSummary.tsx`)

```
Props:
  healthScore: HealthScore
  narrative: NarrativeOutput | null

Layout:
  ┌─ 4 MetricCards in a row ─────────────────────────────────────┐
  │ Intent Accuracy │ Correctness │ Efficiency │ Task Completion  │
  └──────────────────────────────────────────────────────────────┘

  ┌─ AI Assessment CalloutBox (insight variant) ─────────────────┐
  │ narrative.executiveSummary (or "Generate report to see AI     │
  │ analysis" placeholder if narrative is null)                   │
  └──────────────────────────────────────────────────────────────┘

  ┌─ Top Issues (if narrative exists) ───────────────────────────┐
  │ For each narrative.topIssues:                                 │
  │   CalloutBox (danger for P0, warning for P1/P2)              │
  │   Shows: rank, area, description, affected_count, thread ref │
  └──────────────────────────────────────────────────────────────┘

Notes:
  - MetricCards use METRIC_COLOR(value) for dynamic coloring
  - Each card shows: value%, progress bar, "Weight: 25%"
  - If narrative is null, show a muted placeholder — NOT an error
```

---

## Step 4: Verdict Distributions (`VerdictDistributions.tsx`)

```
Props:
  distributions: VerdictDistributions

Layout:
  ┌─ SectionHeader: "2. Verdict Distributions" ─────────────────┐
  └──────────────────────────────────────────────────────────────┘

  ┌─ 2-column grid ─────────────────────────────────────────────┐
  │  LEFT: Correctness Verdict Bar                               │
  │  RIGHT: Efficiency Verdict Bar                               │
  │                                                              │
  │  Use existing DistributionBar component if it accepts        │
  │  custom data. Otherwise, build with Recharts BarChart:       │
  │  - Horizontal stacked bar                                    │
  │  - Colors from VERDICT_COLORS                                │
  │  - Legend below with verdict name + count                    │
  └──────────────────────────────────────────────────────────────┘

  ┌─ Intent Accuracy Histogram ─────────────────────────────────┐
  │  Recharts BarChart (vertical bars)                           │
  │  X-axis: buckets ["0-20", "20-40", ...]                     │
  │  Y-axis: thread count                                        │
  │  Fill: blue-500                                              │
  │  Reference line at average (dashed, red, labeled)            │
  │  Use <ReferenceLine y={avg} stroke="#EF4444" strokeDasharray="3 3" /> │
  │  Annotation: "avg: 93.3%"                                   │
  └──────────────────────────────────────────────────────────────┘

  ┌─ Custom Evaluations (if any) ───────────────────────────────┐
  │  For each customEvaluations entry:                           │
  │  - Numeric: show average as MetricCard + mini histogram      │
  │  - Text: show PieChart (Recharts) with distribution          │
  └──────────────────────────────────────────────────────────────┘

Recharts imports needed:
  import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, Cell, PieChart, Pie, Legend, ReferenceLine,
  } from 'recharts';
```

### Recharts usage pattern (follow existing TrendChart.tsx):
```typescript
<ResponsiveContainer width="100%" height={200}>
  <BarChart data={chartData}>
    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-primary)" />
    <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--text-secondary)' }} />
    <YAxis tick={{ fontSize: 11, fill: 'var(--text-secondary)' }} />
    <Tooltip />
    <Bar dataKey="value">
      {chartData.map((entry, idx) => (
        <Cell key={idx} fill={VERDICT_COLORS[entry.name] || '#94A3B8'} />
      ))}
    </Bar>
  </BarChart>
</ResponsiveContainer>
```

---

## Step 5: Rule Compliance Table (`RuleComplianceTable.tsx`)

```
Props:
  ruleCompliance: RuleComplianceMatrix

Layout:
  ┌─ SectionHeader: "3. Rule Compliance Analysis" ──────────────┐
  └──────────────────────────────────────────────────────────────┘

  ┌─ Table ─────────────────────────────────────────────────────┐
  │ Columns: Rule ID | Section | Pass | Fail | Rate | Severity │
  │                                                              │
  │ - Rule ID: left-aligned, monospace font                      │
  │ - Rate: colored by threshold (green ≥80, amber ≥60, red)   │
  │ - Severity: PriorityBadge-style pill                        │
  │ - Mini progress bar in Rate column (inline, 60px wide)      │
  │ - Rows sorted worst-first (already sorted by backend)       │
  │ - Alternating row backgrounds                                │
  │ - Group by evaluator type (Correctness Rules / Efficiency)  │
  │   using a section header row                                 │
  └──────────────────────────────────────────────────────────────┘

  ┌─ Co-Failure Callouts ───────────────────────────────────────┐
  │  For each coFailure:                                         │
  │  CalloutBox (warning variant)                                │
  │  "When {ruleA} fails, {ruleB} also fails in {rate}% of     │
  │   cases."                                                    │
  │  (Co-failures are already pre-computed by backend with       │
  │   natural language from the AI narrator in Phase 3)          │
  └──────────────────────────────────────────────────────────────┘

Table implementation:
  Use a standard HTML <table> with Tailwind classes — NOT jsPDF autoTable.
  This keeps it consistent with other tables in the app.

  <table className="w-full text-sm">
    <thead>
      <tr className="bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
        <th className="text-left px-3 py-2 font-medium">Rule</th>
        ...
      </tr>
    </thead>
    <tbody>
      {rules.map((rule, i) => (
        <tr key={rule.ruleId}
            className={cn(
              i % 2 === 0 ? 'bg-white dark:bg-[var(--bg-primary)]' : 'bg-[var(--bg-secondary)]',
              rule.rate < 0.5 && 'bg-red-50/50 dark:bg-red-900/10'
            )}>
          ...
        </tr>
      ))}
    </tbody>
  </table>
```

---

## Step 6: Friction Analysis (`FrictionAnalysis.tsx`)

```
Props:
  friction: FrictionAnalysis

Layout:
  ┌─ SectionHeader: "4. Friction & Efficiency Analysis" ────────┐
  └──────────────────────────────────────────────────────────────┘

  ┌─ 3 MetricCards row ─────────────────────────────────────────┐
  │ Total Friction Turns │ Bot-Caused (red) │ User-Caused (blue)│
  └──────────────────────────────────────────────────────────────┘

  ┌─ 2-column charts ───────────────────────────────────────────┐
  │  LEFT: Friction by Cause (PieChart)                          │
  │  - 2 slices: Bot (red), User (blue)                         │
  │  - Inner label showing percentage                            │
  │                                                              │
  │  RIGHT: Recovery Quality (PieChart)                          │
  │  - 3-4 slices: GOOD (green), PARTIAL (amber), FAILED (red) │
  │  - NOT_NEEDED excluded from chart (shown as note)           │
  └──────────────────────────────────────────────────────────────┘

  ┌─ Avg Turns by Verdict (horizontal BarChart) ────────────────┐
  │  Recharts BarChart (layout="vertical")                       │
  │  Y-axis: verdict names                                       │
  │  X-axis: avg turn count                                      │
  │  Each bar colored by verdict color                           │
  │  Value label on bar end                                      │
  └──────────────────────────────────────────────────────────────┘

  ┌─ Top Friction Patterns table ───────────────────────────────┐
  │  # | Pattern Description | Count | Example Threads          │
  │  Row 1 highlighted (most impactful)                          │
  │  Thread IDs as monospace, comma-separated                    │
  └──────────────────────────────────────────────────────────────┘
```

---

## Step 7: Adversarial Breakdown (`AdversarialBreakdown.tsx`)

```
Props:
  adversarial: AdversarialBreakdown

Layout:
  ┌─ SectionHeader: "5. Adversarial Testing Results" ───────────┐
  └──────────────────────────────────────────────────────────────┘

  ┌─ Pass Rate by Category (horizontal stacked BarChart) ───────┐
  │  Y-axis: category names (human-readable)                     │
  │  Green segment: passed, Red segment: failed                  │
  │  Label on right: "3/4 (75%)"                                │
  │  Sorted by pass rate ASC (worst first)                       │
  └──────────────────────────────────────────────────────────────┘

  ┌─ 3 MetricCards: Difficulty breakdown ───────────────────────┐
  │  EASY (green) │ MEDIUM (amber) │ HARD (red)                 │
  │  Each shows: pass_rate%, passed/total                        │
  └──────────────────────────────────────────────────────────────┘

Only rendered when adversarial data exists (conditional in ReportTab).
```

---

## Step 8: Exemplar Threads (`ExemplarThreads.tsx`)

```
Props:
  exemplars: Exemplars
  narrative: NarrativeOutput | null

Layout:
  ┌─ SectionHeader: "6. Exemplar Threads"                       │
  │  Subtitle: "Top 5 best and worst performing threads"        │
  └──────────────────────────────────────────────────────────────┘

  For each exemplar (best first, then worst):

  ┌─ Thread Card ───────────────────────────────────────────────┐
  │                                                              │
  │  ┌─ Card Header ──────────────────────────────────────────┐ │
  │  │  ✓ GOOD EXAMPLE (or ✗ POOR EXAMPLE)  Thread #T-042     │ │
  │  │  bg: green-50 (or red-50), left border colored          │ │
  │  │                                                          │ │
  │  │  VerdictBadge pills:                                     │ │
  │  │  [PASS] [EFFICIENT] [100% Intent] [✓ Task Complete]    │ │
  │  └─────────────────────────────────────────────────────────┘ │
  │                                                              │
  │  ┌─ Transcript ───────────────────────────────────────────┐ │
  │  │  Chat bubble layout:                                     │ │
  │  │                                                          │ │
  │  │  USER message:                                           │ │
  │  │    bg: blue-50, left border: blue-500                    │ │
  │  │    font: monospace, 12px                                 │ │
  │  │                                                          │ │
  │  │  ASSISTANT message:                                      │ │
  │  │    bg: green-50 (good) or red-50 (bad), colored border  │ │
  │  │    font: monospace, 12px                                 │ │
  │  │    Long messages truncated with "Show more" toggle       │ │
  │  └─────────────────────────────────────────────────────────┘ │
  │                                                              │
  │  ┌─ AI Analysis (from narrative.exemplarAnalysis) ────────┐ │
  │  │  CalloutBox:                                             │ │
  │  │  - Good: success variant, title "WHY IT WORKED"          │ │
  │  │  - Bad: danger variant, title "WHAT WENT WRONG"          │ │
  │  │  Content: whatHappened + why                              │ │
  │  │  If promptGap: additional line citing the prompt section │ │
  │  └─────────────────────────────────────────────────────────┘ │
  │                                                              │
  │  ┌─ Rule Violations (bad examples only) ──────────────────┐ │
  │  │  Bullet list of violations:                              │ │
  │  │  ● rule_id — "evidence text" (italic, muted)            │ │
  │  └─────────────────────────────────────────────────────────┘ │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘

Collapsibility:
  - Best examples: first one expanded, rest collapsed
  - Worst examples: first one expanded, rest collapsed
  - Collapse/expand via simple state toggle (chevron icon)

Matching AI analysis to exemplar:
  - Match narrative.exemplarAnalysis[].threadId to exemplar.threadId
  - If no match found (narrator didn't analyze this thread), skip AI analysis section
```

---

## Step 9: Prompt Gap Analysis (`PromptGapAnalysis.tsx`)

```
Props:
  productionPrompts: ProductionPrompts
  narrative: NarrativeOutput | null

Layout:
  ┌─ SectionHeader: "7. Prompt Gap Analysis"                    │
  │  Subtitle: "Mapping production prompt sections to eval       │
  │   rule failures"                                             │
  └──────────────────────────────────────────────────────────────┘

  ┌─ Source ↔ Eval Mapping (static visual) ─────────────────────┐
  │  3 boxes with connecting lines (CSS, not SVG):               │
  │  [Intent Prompt] ──→ [Intent Evaluator]                      │
  │  [Meal Summary]  ──→ [Correctness Evaluator]                 │
  │  [Conv. Flow]    ──→ [Efficiency Evaluator]                  │
  │                                                              │
  │  Implementation: flexbox with dotted border connections      │
  │  Each box: bg-secondary, border, rounded, padding           │
  └──────────────────────────────────────────────────────────────┘

  If narrative?.promptGaps exists and is non-empty:

  ┌─ Gaps Table ────────────────────────────────────────────────┐
  │  Prompt Section | Rule Violated | Gap Type | Description     │
  │                                                              │
  │  Gap Type rendered as colored pill:                          │
  │  UNDERSPEC → blue   SILENT → amber                          │
  │  LEAKAGE → red      CONFLICTING → purple                    │
  └──────────────────────────────────────────────────────────────┘

  ┌─ Suggested Fixes ───────────────────────────────────────────┐
  │  For each gap with a suggestedFix:                           │
  │  CalloutBox (suggest variant)                                │
  │  Title: "Suggested Prompt Patch #{i}"                        │
  │  Target: gap.promptSection                                   │
  │  Body: gap.suggestedFix                                      │
  └──────────────────────────────────────────────────────────────┘

  If no narrative or empty promptGaps:
    Muted placeholder: "AI analysis not available for prompt gaps."
```

---

## Step 10: Recommendations (`Recommendations.tsx`)

```
Props:
  narrative: NarrativeOutput | null

Layout:
  ┌─ SectionHeader: "8. Recommendations" ───────────────────────┐
  └──────────────────────────────────────────────────────────────┘

  If narrative?.recommendations exists:

  For each recommendation (sorted by priority):

  ┌─ Recommendation Card ───────────────────────────────────────┐
  │  ┌──────┐                                                    │
  │  │  P0  │  Action title (bold)                               │
  │  └──────┘  Area: Correctness · Meal Summary Prompt           │
  │                                                              │
  │  "Full action description text here..."                      │
  │                                                              │
  │  ┌─ Impact Badge ────────────────────────────────────────┐   │
  │  │  Expected: -12 failures  (green-50 bg)                │   │
  │  └───────────────────────────────────────────────────────┘   │
  │                                                              │
  │  Card bg: red-50 (P0), amber-50 (P1), blue-50 (P2)         │
  │  Border: matching color, 1px                                 │
  │  Rounded corners                                             │
  └──────────────────────────────────────────────────────────────┘

  ┌─ Disclaimer CalloutBox (info variant) ──────────────────────┐
  │  "AI-generated narratives and recommendations are based on   │
  │   pattern analysis of evaluation data. Projected             │
  │   improvements are estimates. All metrics are computed from  │
  │   this single evaluation run. Larger sample sizes will       │
  │   yield more reliable insights."                             │
  └──────────────────────────────────────────────────────────────┘

  If no narrative:
    Muted placeholder with info callout
```

---

## Step 11: Barrel Export

### `src/features/evalRuns/components/report/index.ts`

```typescript
export { ReportTab } from './ReportTab';
// Individual sections not exported — only ReportTab is the public API
```

---

## Step 12: Wire into RunDetail.tsx

Minimal changes to the existing file:

1. Import `ReportTab` from `./components/report`
2. Add 'report' to tab list (conditional on run status)
3. Render `<ReportTab>` in tab content switch
4. No other changes to RunDetail — all report logic is encapsulated in ReportTab

---

## Verification Checklist

- [ ] "Report" tab appears only for completed batch_thread runs
- [ ] Tab click triggers API call → loading state → rendered report
- [ ] API error shows error callout with retry button
- [ ] All 8 sections render with real data from a completed run
- [ ] Charts render correctly (Recharts — bar, pie, histogram)
- [ ] CalloutBox variants display correct colors and icons
- [ ] MetricCards show dynamic color based on value threshold
- [ ] Rule compliance table sorts worst-first, groups by evaluator type
- [ ] Exemplar thread cards show transcripts with chat bubble styling
- [ ] Long transcripts are truncated with "Show more" toggle
- [ ] Sections with null narrative show muted placeholders (not errors)
- [ ] No layout break at 1024px and 1440px widths
- [ ] `npx tsc -b` passes with zero errors
- [ ] `npm run lint` passes
- [ ] Dark mode: verify all colors use CSS variables (no hardcoded hex in components)

## Component Hierarchy

```
RunDetail.tsx
  └─ ReportTab.tsx
       ├─ ExecutiveSummary.tsx
       │    ├─ MetricCard.tsx (×4)
       │    └─ CalloutBox.tsx (insight)
       ├─ VerdictDistributions.tsx
       │    ├─ Recharts BarChart (×2)
       │    ├─ Recharts BarChart (histogram)
       │    └─ Recharts PieChart (custom evals)
       ├─ RuleComplianceTable.tsx
       │    └─ CalloutBox.tsx (warning, ×N)
       ├─ FrictionAnalysis.tsx
       │    ├─ MetricCard.tsx (×3)
       │    ├─ Recharts PieChart (×2)
       │    └─ Recharts BarChart (horizontal)
       ├─ AdversarialBreakdown.tsx (conditional)
       │    ├─ Recharts BarChart (stacked)
       │    └─ MetricCard.tsx (×3)
       ├─ ExemplarThreads.tsx
       │    ├─ Thread cards (×10)
       │    └─ CalloutBox.tsx (success/danger)
       ├─ PromptGapAnalysis.tsx
       │    └─ CalloutBox.tsx (suggest, ×N)
       └─ Recommendations.tsx
            ├─ Recommendation cards (×N)
            └─ CalloutBox.tsx (info)
```
