import { useState } from 'react';
import { Tabs } from '@/components/ui';
import type { ReportPayload } from '@/types/reports';
import ExecutiveSummary from './ExecutiveSummary';
import VerdictDistributions from './VerdictDistributions';
import RuleComplianceTable from './RuleComplianceTable';
import FrictionAnalysis from './FrictionAnalysis';
import AdversarialBreakdown from './AdversarialBreakdown';
import ExemplarThreads from './ExemplarThreads';
import PromptGapAnalysis from './PromptGapAnalysis';
import Recommendations, { RecommendationsTable } from './Recommendations';
import SectionRail from './SectionRail';
import { CustomEvalTab, CustomSummaryCard } from './customEval';
import { METRIC_COLOR, PRIORITY_DOT_COLORS, rankToPriority } from './shared/colors';
import './report-print.css';

interface Props {
  report: ReportPayload;
  runId: string;
  actions?: React.ReactNode;
}

function gradeHex(grade: string): string {
  if (grade.startsWith('A')) return '#10b981';
  if (grade.startsWith('B')) return '#10b981';
  if (grade.startsWith('C')) return '#f59e0b';
  if (grade.startsWith('D')) return '#ef4444';
  return '#ef4444';
}

export function KairaReportView({ report, runId, actions }: Props) {
  const [activeTab, setActiveTab] = useState('summary');

  const { healthScore, narrative, metadata } = report;
  const isAdversarial = metadata.evalType === 'batch_adversarial';
  const summaryMetrics = isAdversarial
    ? [
      { label: 'Pass Rate', item: healthScore.breakdown.intentAccuracy },
      { label: 'Goal Achievement', item: healthScore.breakdown.correctnessRate },
      { label: 'Rule Compliance', item: healthScore.breakdown.efficiencyRate },
      { label: 'Difficulty Score', item: healthScore.breakdown.taskCompletion },
    ]
    : [
      { label: 'Intent', item: healthScore.breakdown.intentAccuracy },
      { label: 'Correctness', item: healthScore.breakdown.correctnessRate },
      { label: 'Efficiency', item: healthScore.breakdown.efficiencyRate },
      { label: 'Task Completion', item: healthScore.breakdown.taskCompletion },
    ];
  const threadLabel = isAdversarial ? 'tests' : 'threads';

  const formattedDate = new Date(metadata.createdAt).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
  });

  return (
    <div className="relative">
      {/* ── Print-only cover page ── */}
      <div className="print-cover hidden">
        <div
          style={{
            background: '#0f172a',
            color: '#fff',
            padding: '20mm 14mm 12mm',
            marginBottom: '6mm',
            borderRadius: '8px',
          }}
        >
          <div
            style={{
              fontSize: '8px',
              background: '#38bdf8',
              color: '#0f172a',
              display: 'inline-block',
              padding: '2px 8px',
              borderRadius: '10px',
              marginBottom: '8px',
              fontWeight: 700,
              letterSpacing: '0.5px',
            }}
          >
            AI EVALS PLATFORM
          </div>
          <h1 style={{ fontSize: '24px', fontWeight: 'bold', margin: '4px 0' }}>
            {metadata.runName || metadata.appId || 'Evaluation Report'}
          </h1>
          <p style={{ fontSize: '12px', color: '#94a3b8', margin: '4px 0' }}>
            {metadata.evalType} &middot; {metadata.completedThreads} {threadLabel} &middot; {formattedDate}
          </p>
          {metadata.llmModel && (
            <p style={{ fontSize: '9px', color: '#64748b', marginTop: '6px' }}>
              Model: {metadata.llmModel}
            </p>
          )}
          <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '56px',
                height: '56px',
                borderRadius: '50%',
                backgroundColor: gradeHex(healthScore.grade),
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: '20px', fontWeight: 'bold', color: '#fff' }}>
                {healthScore.grade}
              </span>
            </div>
            <div>
              <span style={{ fontSize: '28px', fontWeight: 'bold' }}>
                {Math.round(healthScore.numeric)}
              </span>
              <span style={{ fontSize: '14px', color: '#94a3b8', marginLeft: '4px' }}>/ 100</span>
            </div>
          </div>
        </div>

        {/* Health breakdown cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px', marginBottom: '6mm' }}>
          {summaryMetrics.map(({ label, item }) => (
            <div
              key={label}
              style={{
                border: '1px solid #e2e8f0',
                borderRadius: '6px',
                padding: '8px 10px',
                borderTop: `3px solid ${METRIC_COLOR(item.value)}`,
              }}
            >
              <p style={{ fontSize: '9px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px', margin: '0 0 4px' }}>
                {label}
              </p>
              <p style={{ fontSize: '18px', fontWeight: 'bold', color: METRIC_COLOR(item.value), margin: 0 }}>
                {Math.round(item.value)}%
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="report-container">
        {/* Compact header */}
        <div className="report-actions flex items-center gap-4 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)] px-4 py-2 mb-4">
          {/* Grade circle */}
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm"
            style={{ backgroundColor: gradeHex(healthScore.grade) }}
          >
            <span className="text-white text-sm font-bold">{healthScore.grade}</span>
          </div>
          {/* Score */}
          <div className="h-10 flex items-center">
            <span className="text-xl font-bold text-[var(--text-primary)] leading-none">
              {Math.round(healthScore.numeric)}
            </span>
            <span className="text-sm text-[var(--text-muted)] ml-1.5 leading-none">/ 100</span>
          </div>
          {/* Metadata */}
          <div className="h-10 flex items-center text-xs text-[var(--text-muted)] flex-wrap gap-x-1.5 gap-y-0.5">
            <span>{metadata.completedThreads} {threadLabel}</span>
            <span>&middot;</span>
            <span>{metadata.evalType}</span>
            {metadata.llmModel && (
              <>
                <span>&middot;</span>
                <span>{metadata.llmModel}</span>
              </>
            )}
            <span>&middot;</span>
            <span>{formattedDate}</span>
          </div>
          {/* Action buttons (Export PDF / Refresh) */}
          {actions && <div className="ml-auto shrink-0">{actions}</div>}
        </div>

        {/* Tab layout */}
        <Tabs
          className="report-tabs"
          defaultTab={activeTab}
          onChange={setActiveTab}
          tabs={[
            {
              id: 'summary',
              label: 'Summary',
              content: (
                <div className="space-y-6 pt-2">
                  {/* Compact inline metric row */}
                  <div className="flex flex-wrap items-center gap-6 py-3">
                    {summaryMetrics.map(({ label, item }) => (
                      <div key={label} className="flex items-center gap-2">
                        <span className="text-xs text-[var(--text-muted)]">{label}</span>
                        <span
                          className="text-sm font-bold"
                          style={{ color: METRIC_COLOR(item.value) }}
                        >
                          {Math.round(item.value)}%
                        </span>
                        <div className="w-12 h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${item.value}%`,
                              backgroundColor: METRIC_COLOR(item.value),
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Executive summary prose */}
                  {narrative?.executiveSummary ? (
                    <div className="rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)] px-4 py-3">
                      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
                        {narrative.executiveSummary}
                      </p>
                    </div>
                  ) : (
                    <p className="text-sm text-[var(--text-muted)] italic">
                      AI narrative was not generated for this report.
                    </p>
                  )}

                  {/* Top Issues */}
                  {narrative?.topIssues && narrative.topIssues.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">Top Issues</h3>
                      <div className="overflow-x-auto rounded border border-[var(--border-subtle)]">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b-2 border-[var(--border-subtle)]">
                              <th style={{ width: 12 }} className="px-2 py-1.5" />
                              <th className="text-left px-2 py-1.5 text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">Issue</th>
                              <th className="text-left px-2 py-1.5 text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">Focus Area</th>
                              <th className="text-right px-2 py-1.5 text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider whitespace-nowrap">{isAdversarial ? 'Tests Affected' : 'Threads Affected'}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {narrative.topIssues.map((issue, i) => {
                              const priority = rankToPriority(issue.rank);
                              return (
                                <tr key={issue.rank} className={i % 2 === 0 ? 'bg-[var(--bg-primary)]' : 'bg-[var(--bg-secondary)]'}>
                                  <td className="px-2 py-2 align-top">
                                    <span
                                      className="inline-block w-2 h-2 rounded-full"
                                      style={{ backgroundColor: PRIORITY_DOT_COLORS[priority] }}
                                    />
                                  </td>
                                  <td className="px-2 py-2 align-top font-semibold text-[var(--text-primary)]">{issue.description}</td>
                                  <td className="px-2 py-2 align-top whitespace-nowrap text-[var(--text-muted)]">{issue.area}</td>
                                  <td className="px-2 py-2 align-top text-right text-[var(--text-muted)] whitespace-nowrap">{issue.affectedCount}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Custom Evaluations summary preview */}
                  {report.customEvaluationsReport && (
                    <CustomSummaryCard
                      report={report.customEvaluationsReport}
                      onNavigate={() => setActiveTab('custom')}
                    />
                  )}

                  {/* Top 3 Recommendations */}
                  {narrative?.recommendations && narrative.recommendations.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">Top Recommendations</h3>
                      <RecommendationsTable items={narrative.recommendations.slice(0, 3)} />
                    </div>
                  )}
                </div>
              ),
            },
            {
              id: 'detailed',
              label: 'Detailed Analysis',
              content: (
                <div className="report-detailed-sections pt-2">
                  <SectionRail pageKey="detailed" />
                  <div className="space-y-8">
                    <ExecutiveSummary healthScore={report.healthScore} narrative={report.narrative} isAdversarial={isAdversarial} />
                    <VerdictDistributions distributions={report.distributions} isAdversarial={isAdversarial} adversarialBreakdown={report.adversarial} />
                    <RuleComplianceTable ruleCompliance={report.ruleCompliance} />
                    {!isAdversarial && <FrictionAnalysis friction={report.friction} runId={runId} />}
                    {(isAdversarial || report.adversarial) && report.adversarial && (
                      <AdversarialBreakdown adversarial={report.adversarial} />
                    )}
                    <ExemplarThreads exemplars={report.exemplars} narrative={report.narrative} isAdversarial={isAdversarial} runId={runId} />
                    <PromptGapAnalysis narrative={report.narrative} />
                    <Recommendations narrative={report.narrative} />
                  </div>
                </div>
              ),
            },
            ...(report.customEvaluationsReport ? [{
              id: 'custom',
              label: 'Custom Evaluations',
              content: <CustomEvalTab report={report.customEvaluationsReport} />,
            }] : []),
          ]}
        />
      </div>

      {/* Print-only footer */}
      <div className="print-footer print-only hidden">
        CONFIDENTIAL &mdash; AI Evals Platform &middot; Tatvacare
      </div>
    </div>
  );
}
