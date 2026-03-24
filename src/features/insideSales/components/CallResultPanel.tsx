import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/utils';
import { scoreColor } from '@/utils/scoreUtils';
import { AudioPlayer } from '@/features/transcript/components/AudioPlayer';
import type { ThreadEvalRow, AppId } from '@/types';

interface CallResultPanelProps {
  thread: ThreadEvalRow;
  recordingUrl?: string;
  appId?: AppId;
}

export function CallResultPanel({ thread, recordingUrl, appId }: CallResultPanelProps) {
  const [activeTab, setActiveTab] = useState<'scorecard' | 'compliance'>('scorecard');

  const result = thread.result as unknown as Record<string, unknown> | undefined;
  const evals = result?.evaluations as Array<Record<string, unknown>> | undefined;
  const evalOutput = evals?.[0]?.output as Record<string, unknown> | undefined;
  const reasoning = evalOutput?.reasoning as string | undefined;
  const transcript = result?.transcript as string | undefined;

  // Overall score
  let overallScore: number | null = null;
  if (evalOutput && typeof evalOutput.overall_score === 'number') {
    overallScore = evalOutput.overall_score;
  } else {
    const topOutput = result?.output as Record<string, unknown> | undefined;
    if (topOutput && typeof topOutput.overall_score === 'number') {
      overallScore = topOutput.overall_score;
    }
  }

  // Dimension scores (numeric fields, excluding overall_score and reasoning)
  const dimensions = evalOutput
    ? Object.entries(evalOutput).filter(
        ([k, v]) => typeof v === 'number' && k !== 'overall_score'
      )
    : [];

  // Compliance gates (boolean fields)
  const complianceGates = evalOutput
    ? Object.entries(evalOutput).filter(([, v]) => typeof v === 'boolean')
    : [];

  // Split pane content
  return (
    <>
      {/* Split pane: transcript left, scorecard/compliance right — md+ */}
      <div className="hidden md:flex flex-1 min-h-0">
        {/* Left: transcript */}
        <div className="w-[35%] min-w-[280px] max-w-[420px] flex flex-col min-h-0 border-r border-[var(--border-subtle)]">
          <div className="px-3 py-2 border-b border-[var(--border-subtle)] text-xs font-semibold text-[var(--text-muted)] uppercase">
            Transcript
          </div>
          {recordingUrl && appId && (
            <div className="shrink-0 px-3 py-2 border-b border-[var(--border-subtle)]">
              <AudioPlayer audioUrl={recordingUrl} appId={appId} />
            </div>
          )}
          <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2">
            {transcript ? (
              <div className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed font-mono">
                {transcript}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-muted)] py-4 text-center">No transcript available.</p>
            )}
          </div>
        </div>

        {/* Right: tabs */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0">
          {/* Tab bar */}
          <div className="flex border-b border-[var(--border-subtle)]">
            {(['scorecard', 'compliance'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  'px-4 py-2 text-xs font-semibold transition-colors border-b-2',
                  activeTab === tab
                    ? 'border-[var(--interactive-primary)] text-[var(--text-brand)]'
                    : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                )}
              >
                {tab === 'scorecard' ? 'Scorecard' : 'Compliance'}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
            {activeTab === 'scorecard' && (
              <div className="space-y-0">
                {dimensions.map(([key, val]) => {
                  const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                  const score = val as number;
                  const pctVal = Math.min(100, Math.max(0, score * 100 / (score <= 15 ? 15 : 100)));
                  return (
                    <div key={key} className="flex items-center gap-2 py-2 border-b border-[var(--border-subtle)] last:border-b-0">
                      <span className="text-xs text-[var(--text-primary)] w-[45%] shrink-0">{label}</span>
                      <div className="flex-1 h-2 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${pctVal}%`,
                            background: score >= 8 ? 'var(--color-success)' : score >= 5 ? 'var(--color-warning)' : 'var(--color-error)',
                          }}
                        />
                      </div>
                      <span className="text-xs font-bold w-12 text-right" style={{ color: scoreColor(score) }}>
                        {score}
                      </span>
                    </div>
                  );
                })}
                {/* Total row */}
                {overallScore !== null && (
                  <div className="flex items-center justify-between mt-3 px-3 py-2.5 bg-[var(--bg-secondary)] rounded-md border border-[var(--border-subtle)]">
                    <span className="text-[13px] font-semibold text-[var(--text-primary)]">Total</span>
                    <span className="text-lg font-bold" style={{ color: scoreColor(overallScore) }}>
                      {overallScore}/100
                    </span>
                  </div>
                )}
                {/* Reasoning */}
                {reasoning && (
                  <div className="mt-4 pt-3 border-t border-[var(--border-subtle)]">
                    <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">Reasoning</h4>
                    <div className="text-xs text-[var(--text-secondary)] leading-relaxed prose prose-sm prose-invert max-w-none [&_strong]:text-[var(--text-primary)] [&_p]:mb-2 [&_ol]:pl-4 [&_li]:mb-1">
                      <ReactMarkdown>{reasoning}</ReactMarkdown>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'compliance' && (
              <div>
                {/* Filter chips */}
                <div className="flex flex-wrap gap-1 pb-3">
                  <span className="px-2 py-0.5 text-xs rounded-full border border-[var(--border-brand)] bg-[var(--surface-info)] text-[var(--text-brand)]">
                    All ({complianceGates.length})
                  </span>
                  <span className="px-2 py-0.5 text-xs rounded-full border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                    Violations ({complianceGates.filter(([, v]) => !v).length})
                  </span>
                  <span className="px-2 py-0.5 text-xs rounded-full border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                    Passed ({complianceGates.filter(([, v]) => v).length})
                  </span>
                </div>
                {/* Compliance table */}
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border-subtle)]">
                      <th className="text-center w-12 py-1.5 px-2 font-semibold text-[var(--text-muted)]">Status</th>
                      <th className="text-left py-1.5 px-2 font-semibold text-[var(--text-muted)]">Rule</th>
                    </tr>
                  </thead>
                  <tbody>
                    {complianceGates.map(([key, val]) => {
                      const label = key.replace(/^compliance_/, '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                      const passed = val as boolean;
                      return (
                        <tr key={key} className="border-b border-[var(--border-subtle)]">
                          <td className="text-center py-2 px-2">
                            <span className={cn(
                              'inline-flex items-center justify-center w-5 h-5 rounded-full text-[11px] font-bold',
                              passed ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'
                            )}>
                              {passed ? '\u2713' : '\u2717'}
                            </span>
                          </td>
                          <td className="py-2 px-2">
                            <span className={cn(
                              'text-[13px] font-semibold',
                              passed ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]'
                            )}>
                              {label}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile: stacked */}
      <div className="flex flex-col flex-1 min-h-0 md:hidden space-y-3 overflow-y-auto">
        {recordingUrl && appId && (
          <div className="shrink-0 px-1">
            <AudioPlayer audioUrl={recordingUrl} appId={appId} />
          </div>
        )}
        {transcript && (
          <details className="shrink-0">
            <summary className="text-xs text-[var(--text-muted)] font-medium cursor-pointer py-1.5 px-1">
              Transcript
            </summary>
            <div className="max-h-[300px] overflow-y-auto px-2 py-1">
              <div className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed font-mono">
                {transcript}
              </div>
            </div>
          </details>
        )}
        {dimensions.length > 0 && (
          <div className="px-2">
            {dimensions.map(([key, val]) => {
              const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
              const score = val as number;
              return (
                <div key={key} className="flex items-center justify-between py-1.5 border-b border-[var(--border-subtle)] text-xs">
                  <span className="text-[var(--text-secondary)]">{label}</span>
                  <span className="font-bold" style={{ color: scoreColor(score) }}>{score}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
