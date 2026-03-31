export interface InsideSalesRunSlice {
  runId: string;
  runName: string | null;
  createdAt: string;
  avgQaScore: number;
  compliancePassRate: number;
  evaluatedCalls: number;
  totalCalls: number;
}

export interface InsideSalesCrossRunStats {
  totalRuns: number;
  allRuns: number;
  totalCalls: number;
  evaluatedCalls: number;
  avgQaScore: number;
  avgCompliancePassRate: number;
  avgDimensionScores: Record<string, number>;
}

export interface InsideSalesTrendPoint {
  runId: string;
  runName: string | null;
  createdAt: string;
  avgQaScore: number;
  compliancePassRate: number;
  evaluatedCalls: number;
  dimensionScores: Record<string, number>;
}

export interface InsideSalesDimensionHeatmapRow {
  key: string;
  label: string;
  avgScore: number;
  maxPossible: number;
  greenThreshold: number;
  yellowThreshold: number;
  cells: Array<number | null>;
}

export interface InsideSalesDimensionHeatmap {
  runs: InsideSalesRunSlice[];
  rows: InsideSalesDimensionHeatmapRow[];
}

export interface InsideSalesComplianceHeatmapRow {
  key: string;
  label: string;
  avgPassRate: number;
  cells: Array<number | null>;
}

export interface InsideSalesComplianceHeatmap {
  runs: InsideSalesRunSlice[];
  rows: InsideSalesComplianceHeatmapRow[];
}

export interface InsideSalesFlagRollup {
  label: string;
  relevant: number;
  notRelevant: number;
  present: number;
  attempted: number;
  accepted: number;
}

export interface InsideSalesFlagRollups {
  behavioral: Record<string, InsideSalesFlagRollup>;
  outcomes: Record<string, InsideSalesFlagRollup>;
}

export interface InsideSalesAggregatedIssue {
  area: string;
  descriptions: string[];
  totalAffected: number;
  runCount: number;
  worstRank: number;
}

export interface InsideSalesAggregatedRecommendation {
  area: string;
  highestPriority: string;
  actions: string[];
  runCount: number;
  estimatedImpacts: string[];
}

export interface InsideSalesIssuesAndRecommendations {
  issues: InsideSalesAggregatedIssue[];
  recommendations: InsideSalesAggregatedRecommendation[];
  runsWithNarrative: number;
  runsWithoutNarrative: number;
}

export interface InsideSalesCrossRunAnalytics {
  stats: InsideSalesCrossRunStats;
  scoreTrend: InsideSalesTrendPoint[];
  dimensionHeatmap: InsideSalesDimensionHeatmap;
  complianceHeatmap: InsideSalesComplianceHeatmap;
  flagRollups: InsideSalesFlagRollups;
  issuesAndRecommendations: InsideSalesIssuesAndRecommendations;
}
