/**
 * Pure transformation functions that convert canonical PlatformReportSection data
 * into the prop shapes expected by rich shared components.
 * Used by PlatformReportRenderer — no app-specific logic.
 */
import type {
  ComplianceTableSection,
  DistributionChartSection,
  ExemplarsSection,
  IssuesRecommendationsSection,
  NarrativeSection,
  PlatformCrossRunNarrative,
  PlatformRunNarrative,
  PlatformRunReportPayload,
  PromptGapAnalysisSection,
} from '@/types/platformReports';
import type {
  AdversarialBreakdown,
  ExemplarAnalysis,
  ExemplarThread,
  Exemplars,
  NarrativeOutput,
  PromptGap,
  RuleComplianceMatrix,
  VerdictDistributions as LegacyVerdictDistributions,
} from '@/types/reports';

// ── helpers ──────────────────────────────────────────────

function readString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function readNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function readBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function readTranscript(value: unknown): ExemplarThread['transcript'] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const role = readString((item as Record<string, unknown>).role);
    const content = readString((item as Record<string, unknown>).content);
    return (role === 'user' || role === 'assistant') && content ? [{ role, content }] : [];
  });
}

function readRuleViolations(value: unknown): ExemplarThread['ruleViolations'] {
  if (typeof value === 'string') {
    return value.split(',').map((s) => s.trim()).filter(Boolean).map((ruleId) => ({ ruleId, evidence: '' }));
  }
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const ruleId = readString((item as Record<string, unknown>).ruleId);
    if (!ruleId) return [];
    return [{ ruleId, evidence: readString((item as Record<string, unknown>).evidence) ?? '' }];
  });
}

function readFrictionTurns(value: unknown): ExemplarThread['frictionTurns'] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const turn = readNumber((item as Record<string, unknown>).turn);
    const cause = readString((item as Record<string, unknown>).cause);
    const description = readString((item as Record<string, unknown>).description);
    return turn != null && cause && description ? [{ turn, cause: cause as 'bot' | 'user', description }] : [];
  });
}

function readStringList(value: unknown): string[] {
  if (typeof value === 'string') return value.split(',').map((s) => s.trim()).filter(Boolean);
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => (typeof item === 'string' ? [item] : []));
}

function parseSummaryField(summary: string, field: string): string | null {
  const match = summary.match(new RegExp(`${field}=([^,]+)`));
  return match?.[1]?.trim() ?? null;
}

function readTaskCompleted(details: Record<string, unknown>, summary: string): boolean {
  const explicit = readBoolean(details.taskCompleted);
  if (explicit != null) return explicit;
  const fallback = parseSummaryField(summary, 'Task completed');
  return fallback === 'True' || fallback === 'true';
}

type PriorityKey = 'P0' | 'P1' | 'P2';

export function normalizePriority(value: string | null | undefined, fallbackIndex = 0): PriorityKey {
  const normalized = (value ?? '').trim().toUpperCase();
  if (normalized === 'P0' || normalized === 'CRITICAL' || normalized === 'HIGH') return 'P0';
  if (normalized === 'P1' || normalized === 'MEDIUM') return 'P1';
  if (normalized === 'P2' || normalized === 'LOW') return 'P2';
  return fallbackIndex === 0 ? 'P0' : fallbackIndex < 3 ? 'P1' : 'P2';
}

function distributionSeriesKey(series: DistributionChartSection['data'][number]): string {
  return ((series as { key?: string }).key ?? series.label).toLowerCase();
}

function splitAnalysis(text: string): { whatHappened: string; why: string } {
  const parts = text.split(/(?<=[.!?])\s+/).filter(Boolean);
  if (parts.length >= 2) return { whatHappened: parts[0], why: parts.slice(1).join(' ') };
  return { whatHappened: text, why: text };
}

// ── public transforms ────────────────────────────────────

export function transformDistributions(section: DistributionChartSection | null): LegacyVerdictDistributions {
  const distributions: LegacyVerdictDistributions = {
    correctness: {},
    efficiency: {},
    adversarial: null,
    intentHistogram: { buckets: [], counts: [] },
  };
  for (const series of section?.data ?? []) {
    const key = distributionSeriesKey(series);
    const values = Object.fromEntries(series.categories.map((c, i) => [c, series.values[i] ?? 0]));
    if (key === 'correctness') { distributions.correctness = values; continue; }
    if (key === 'efficiency') { distributions.efficiency = values; continue; }
    if (key === 'adversarial') { distributions.adversarial = values; continue; }
    if (key === 'intent' || key === 'intent-histogram') {
      distributions.intentHistogram = { buckets: [...series.categories], counts: [...series.values] };
    }
  }
  return distributions;
}

export function transformAdversarialBreakdown(section: DistributionChartSection | null): AdversarialBreakdown | null {
  const byGoal = (section?.data ?? [])
    .filter((s) => distributionSeriesKey(s).startsWith('goal:') && s.values.length > 0)
    .map((s) => {
      const passRate = s.values[0] ?? 0;
      return { goal: s.label, passed: Math.round((passRate / 100) * 100), total: 100, passRate: passRate / 100 };
    });
  const byDifficulty = (section?.data ?? [])
    .filter((s) => distributionSeriesKey(s).startsWith('difficulty:') && s.values.length > 0)
    .map((s) => {
      const passed = Math.round(s.values[0] ?? 0);
      const failed = Math.round(s.values[1] ?? 0);
      return { difficulty: s.label, passed, total: passed + failed };
    });
  if (byGoal.length === 0 && byDifficulty.length === 0) return null;
  return { byGoal, byDifficulty };
}

export function transformCompliance(section: ComplianceTableSection | null): RuleComplianceMatrix {
  return {
    rules: (section?.data ?? []).map((row) => ({
      ruleId: row.label || row.key,
      section: row.section || row.label || row.key,
      passed: row.passed,
      failed: row.failed,
      notEvaluated: row.notEvaluated ?? 0,
      rate: row.rate > 1 ? row.rate / 100 : row.rate,
      severity: (row.severity?.toUpperCase() as 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | undefined) ?? 'LOW',
    })),
    coFailures: (section?.coFailures ?? []).map((cf) => ({
      ruleA: cf.ruleA,
      ruleB: cf.ruleB,
      coOccurrenceRate: cf.coOccurrenceRate,
    })),
  };
}

export function transformExemplars(section: ExemplarsSection | null): Exemplars {
  const exemplars: Exemplars = { best: [], worst: [] };
  for (const item of section?.data ?? []) {
    const details = item.details ?? {};
    const bucket = details.type === 'worst' ? 'worst' : 'best';
    const thread: ExemplarThread = {
      threadId: item.itemId,
      compositeScore: item.score ?? 0,
      intentAccuracy: readNumber(details.intentAccuracy),
      correctnessVerdict: readString(details.correctnessVerdict) ?? parseSummaryField(item.summary, 'Correctness'),
      efficiencyVerdict: readString(details.efficiencyVerdict) ?? parseSummaryField(item.summary, 'Efficiency'),
      taskCompleted: readTaskCompleted(details, item.summary),
      transcript: readTranscript(details.transcript),
      ruleViolations: readRuleViolations(details.ruleViolations),
      frictionTurns: readFrictionTurns(details.frictionTurns),
      goalFlow: readStringList(details.goalFlow),
      activeTraits: readStringList(details.activeTraits),
      difficulty: readString(details.difficulty) ?? undefined,
      failureModes: readStringList(details.failureModes),
      reasoning: readString(details.reasoning) ?? undefined,
      goalAchieved: readBoolean(details.goalAchieved) ?? undefined,
    };
    exemplars[bucket].push(thread);
  }
  return exemplars;
}

export function transformNarrative(
  report: PlatformRunReportPayload,
): NarrativeOutput | null {
  const narrativeSection = report.sections.find((s) => s.type === 'narrative') as NarrativeSection | undefined;
  const recSection = report.sections.find((s) => s.type === 'issues_recommendations') as IssuesRecommendationsSection | undefined;
  const gapSection = report.sections.find((s) => s.type === 'prompt_gap_analysis') as PromptGapAnalysisSection | undefined;

  const narrative = narrativeSection?.data as PlatformRunNarrative | undefined;
  if (!narrative && !recSection && !gapSection) return null;

  const issues = recSection?.data.issues ?? [];
  const recommendations = recSection?.data.recommendations ?? [];
  const exemplarAnalysis = (narrative?.exemplars ?? []).map((item): ExemplarAnalysis => {
    const split = splitAnalysis(item.analysis);
    return {
      threadId: item.itemId,
      type: item.label.toLowerCase().includes('worst') ? 'bad' : 'good',
      whatHappened: split.whatHappened,
      why: split.why,
      promptGap: null,
    };
  });

  return {
    executiveSummary: narrative?.executiveSummary ?? '',
    topIssues: issues.map((item, index) => ({
      rank: index + 1,
      area: item.area,
      description: item.summary || item.title,
      affectedCount: item.affectedCount ?? 0,
      exampleThreadId: null,
    })),
    exemplarAnalysis,
    promptGaps: (gapSection?.data ?? narrative?.promptGaps ?? []).map((item) => ({
      promptSection: item.promptSection,
      evalRule: item.evaluationRule,
      gapType: item.gapType as PromptGap['gapType'],
      description: 'summary' in item ? item.summary : '',
      suggestedFix: item.suggestedFix ?? '',
    })),
    recommendations: recommendations.map((item) => ({
      priority: normalizePriority(item.priority),
      area: item.title || item.action,
      action: item.action,
      estimatedImpact: item.expectedImpact ?? '',
    })),
  };
}

/**
 * Cross-run analogue of {@link transformNarrative}: maps the cross-run
 * narrative's critical patterns and strategic recommendations into the same
 * {@link NarrativeOutput} shape, so the cross-run report reuses the exact
 * single-run Summary components (top-issues table + Recommendations) instead
 * of bespoke stacked blocks.
 */
export function transformCrossRunNarrative(
  narrative: PlatformCrossRunNarrative,
): NarrativeOutput {
  return {
    executiveSummary: narrative.executiveSummary ?? '',
    topIssues: (narrative.criticalPatterns ?? []).map((item, index) => ({
      rank: index + 1,
      area: item.title,
      description: item.summary,
      affectedCount: item.affectedRuns ?? 0,
      exampleThreadId: null,
    })),
    exemplarAnalysis: [],
    promptGaps: [],
    recommendations: (narrative.strategicRecommendations ?? []).map((item, index) => ({
      priority: normalizePriority(item.priority, index),
      area: '',
      action: item.action,
      estimatedImpact: item.expectedImpact ?? '',
    })),
  };
}
