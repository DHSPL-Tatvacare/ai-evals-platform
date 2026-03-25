import { useMemo, useState } from 'react';
import { DimensionBreakdownChart } from '@/components/report/DimensionBreakdownChart';
import { FlagStatsPanel } from '@/components/report/FlagStatsPanel';
import { ComplianceGatesPanel } from '@/components/report/ComplianceGatesPanel';
import type { InsideSalesReportPayload } from '@/types/insideSalesReport';
import { cn } from '@/utils/cn';
import { AgentHeatmapTable } from './AgentHeatmapTable';

interface Props {
  report: InsideSalesReportPayload;
}

function verdictColor(score: number): string {
  if (score >= 80) return 'text-[var(--color-success)]';
  if (score >= 65) return 'text-[var(--color-warning)]';
  return 'text-[var(--color-error)]';
}

export function InsideSalesReportView({ report }: Props) {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  const activeSlice = selectedAgentId ? report.agentSlices[selectedAgentId] : null;

  const dimensions = useMemo(() => {
    return Object.entries(report.dimensionBreakdown).map(([key, dim]) => ({
      key,
      label: dim.label,
      avg: activeSlice ? (activeSlice.dimensions[key]?.avg ?? 0) : dim.avg,
      maxPossible: dim.maxPossible,
      greenThreshold: dim.greenThreshold,
      yellowThreshold: dim.yellowThreshold,
    }));
  }, [report.dimensionBreakdown, activeSlice]);

  const complianceGates = useMemo(() => {
    return Object.entries(report.complianceBreakdown).map(([key, gate]) => ({
      key,
      label: gate.label,
      passed: gate.passed,
      failed: gate.failed,
      total: gate.total,
    }));
  }, [report.complianceBreakdown]);

  const flagData = activeSlice?.flags ?? report.flagStats;
  const summary = activeSlice
    ? { avgQaScore: activeSlice.avgQaScore, callCount: activeSlice.callCount, verdictDistribution: activeSlice.verdictDistribution }
    : { avgQaScore: report.runSummary.avgQaScore, callCount: report.runSummary.evaluatedCalls, verdictDistribution: report.runSummary.verdictDistribution };

  const totalCalls = activeSlice ? activeSlice.callCount : report.runSummary.totalCalls;

  const verdictBars = [
    { key: 'strong', label: 'Strong', color: 'bg-[var(--color-success)]' },
    { key: 'good', label: 'Good', color: 'bg-[var(--color-warning)]' },
    { key: 'needsWork', label: 'Needs Work', color: 'bg-orange-500' },
    { key: 'poor', label: 'Poor', color: 'bg-[var(--color-error)]' },
  ] as const;

  return (
    <div className="space-y-8">
      {/* Section 1: Executive Summary */}
      <section>
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div className="bg-[var(--bg-primary)] p-4 rounded-lg border border-[var(--border)] text-center">
            <div className="text-[11px] uppercase text-[var(--text-secondary)]">Avg QA Score</div>
            <div className={cn('text-3xl font-bold', verdictColor(summary.avgQaScore))}>
              {summary.avgQaScore.toFixed(1)}
            </div>
            <div className="text-xs text-[var(--text-secondary)]">{summary.callCount} calls evaluated</div>
          </div>
          <div className="bg-[var(--bg-primary)] p-4 rounded-lg border border-[var(--border)] text-center">
            <div className="text-[11px] uppercase text-[var(--text-secondary)]">Compliance</div>
            <div className={cn('text-3xl font-bold', report.runSummary.compliancePassRate >= 90 ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]')}>
              {report.runSummary.compliancePassRate.toFixed(0)}%
            </div>
            <div className="text-xs text-[var(--text-secondary)]">
              {report.runSummary.complianceViolationCount} violations
            </div>
          </div>
          <div className="bg-[var(--bg-primary)] p-4 rounded-lg border border-[var(--border)] text-center">
            <div className="text-[11px] uppercase text-[var(--text-secondary)]">Verdict</div>
            <div className="flex justify-center gap-1 mt-2">
              {verdictBars.map((v) => {
                const count = summary.verdictDistribution[v.key];
                return (
                  <div key={v.key} className="text-center">
                    <div className={cn('w-6 rounded', v.color)} style={{ height: Math.max(8, count * 2) }} />
                    <div className="text-[10px] mt-0.5">{count}</div>
                  </div>
                );
              })}
            </div>
            <div className="text-[10px] text-[var(--text-secondary)] mt-1">Strong · Good · Needs Work · Poor</div>
          </div>
        </div>

        {report.narrative?.executiveSummary && (
          <div className="bg-[var(--bg-primary)] p-4 rounded-lg border-l-2 border-[var(--accent)] text-sm leading-relaxed text-[var(--text-secondary)]">
            <div className="text-[11px] uppercase text-[var(--accent)] mb-2">AI Summary</div>
            {report.narrative.executiveSummary}
          </div>
        )}
      </section>

      {/* Section 2: Dimension Breakdown */}
      <section>
        <h3 className="text-sm font-semibold mb-3">QA Dimension Breakdown</h3>
        <DimensionBreakdownChart dimensions={dimensions} />
      </section>

      {/* Section 3: Agent Heatmap */}
      <section>
        <h3 className="text-sm font-semibold mb-3">Agent Performance</h3>
        <AgentHeatmapTable
          agentSlices={report.agentSlices}
          dimensionBreakdown={report.dimensionBreakdown}
          selectedAgentId={selectedAgentId}
          onAgentSelect={setSelectedAgentId}
          coachingNote={selectedAgentId ? report.narrative?.agentCoachingNotes[selectedAgentId] : null}
        />
      </section>

      {/* Section 4: Flags */}
      <section>
        <h3 className="text-sm font-semibold mb-3">Behavioral Signals & Outcomes</h3>
        <FlagStatsPanel
          behavioralFlags={[
            { key: 'escalation', label: 'Escalations', ...flagData.escalation, color: 'text-[var(--color-error)]' },
            { key: 'disagreement', label: 'Disagreements', ...flagData.disagreement, color: 'text-[var(--color-warning)]' },
            { key: 'tension', label: 'Tension Moments', relevant: flagData.tension.relevant, notRelevant: flagData.tension.notRelevant, present: Object.values(flagData.tension.bySeverity).reduce((a, b) => a + b, 0), color: 'text-[var(--color-warning)]' },
          ]}
          outcomeFlags={[
            { key: 'meetingSetup', label: 'Meeting Setup', ...flagData.meetingSetup, total: totalCalls },
            { key: 'purchaseMade', label: 'Purchase', ...flagData.purchaseMade, total: totalCalls },
            { key: 'callbackScheduled', label: 'Callback', ...flagData.callbackScheduled, total: totalCalls },
            { key: 'crossSell', label: 'Cross-sell', ...flagData.crossSell, total: totalCalls },
          ]}
        />
      </section>

      {/* Section 5: Compliance */}
      <section>
        <h3 className="text-sm font-semibold mb-3">Compliance</h3>
        <ComplianceGatesPanel gates={complianceGates} />
      </section>

      {/* Section 7: Recommendations */}
      {report.narrative?.recommendations && report.narrative.recommendations.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold mb-3">Recommendations</h3>
          <div className="space-y-3">
            {report.narrative.recommendations.map((rec, i) => {
              const colors: Record<string, string> = { P0: 'bg-[var(--color-error)]', P1: 'bg-orange-500', P2: 'bg-[var(--color-warning)]' };
              return (
                <div key={i} className="flex gap-3 items-start">
                  <span className={cn('text-white px-2 py-0.5 rounded text-[11px] font-semibold flex-shrink-0', colors[rec.priority] || 'bg-gray-500')}>
                    {rec.priority}
                  </span>
                  <span className="text-sm">{rec.action}</span>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
