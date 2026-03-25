// src/types/insideSalesReport.ts
// Types for inside sales report payload. Separate from reports.ts (Kaira).

export interface DimensionStats {
  label: string;
  avg: number;
  min: number;
  max: number;
  maxPossible: number;
  greenThreshold: number;
  yellowThreshold: number;
  distribution: number[];
}

export interface ComplianceGateStats {
  label: string;
  passed: number;
  failed: number;
  total: number;
}

export interface FlagStat {
  relevant: number;
  notRelevant: number;
  present: number;
}

export interface OutcomeFlagStat {
  relevant: number;
  notRelevant: number;
  attempted: number;
  accepted: number;
}

export interface TensionFlagStat {
  relevant: number;
  notRelevant: number;
  bySeverity: Record<string, number>;
}

export interface FlagStats {
  escalation: FlagStat;
  disagreement: FlagStat;
  tension: TensionFlagStat;
  meetingSetup: OutcomeFlagStat;
  purchaseMade: OutcomeFlagStat;
  callbackScheduled: OutcomeFlagStat;
  crossSell: OutcomeFlagStat;
}

export interface VerdictDistribution {
  strong: number;
  good: number;
  needsWork: number;
  poor: number;
}

export interface RunSummary {
  totalCalls: number;
  evaluatedCalls: number;
  avgQaScore: number;
  verdictDistribution: VerdictDistribution;
  compliancePassRate: number;
  complianceViolationCount: number;
}

export interface AgentSlice {
  agentName: string;
  callCount: number;
  avgQaScore: number;
  dimensions: Record<string, { avg: number }>;
  compliance: { passed: number; failed: number };
  flags: FlagStats;
  verdictDistribution: VerdictDistribution;
}

export interface DimensionInsight {
  dimension: string;
  insight: string;
  priority: string;
}

export interface Recommendation {
  priority: string;
  action: string;
}

export interface InsideSalesNarrative {
  executiveSummary: string;
  dimensionInsights: DimensionInsight[];
  agentCoachingNotes: Record<string, string>;
  flagPatterns: string;
  complianceAlerts: string[];
  recommendations: Recommendation[];
}

export interface InsideSalesReportMetadata {
  runId: string;
  runName: string | null;
  appId: string;
  evalType: string;
  createdAt: string;
  llmProvider: string | null;
  llmModel: string | null;
  narrativeModel: string | null;
  totalCalls: number;
  evaluatedCalls: number;
  durationMs: number | null;
}

export interface InsideSalesReportPayload {
  metadata: InsideSalesReportMetadata;
  runSummary: RunSummary;
  dimensionBreakdown: Record<string, DimensionStats>;
  complianceBreakdown: Record<string, ComplianceGateStats>;
  flagStats: FlagStats;
  agentSlices: Record<string, AgentSlice>;
  narrative: InsideSalesNarrative | null;
}
