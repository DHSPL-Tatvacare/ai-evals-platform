/**
 * ScorecardTab — expandable dimension scorecard for call quality evaluation.
 * Shows per-dimension scores with progress bars, per-check evidence, and critique.
 */

import { useState } from 'react';
import { ChevronDown, ChevronRight, Check, Minus, X } from 'lucide-react';

interface CheckResult {
  name: string;
  pointsAwarded: number;
  maxPoints: number;
  evidence: string;
}

interface DimensionResult {
  score: number;
  maxScore: number;
  critique: string;
  checks: CheckResult[];
}

interface ScorecardTabProps {
  overallScore: number | null;
  dimensions: Record<string, DimensionResult>;
}

export function ScorecardTab({ overallScore, dimensions }: ScorecardTabProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleDimension = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const entries = Object.entries(dimensions);

  if (entries.length === 0) {
    return (
      <div className="text-center py-8 text-xs text-[var(--text-muted)]">
        No dimension scores available.
      </div>
    );
  }

  return (
    <div className="space-y-1.5 py-2">
      {entries.map(([key, dim]) => {
        const isOpen = expanded.has(key);
        const pct = dim.maxScore > 0 ? (dim.score / dim.maxScore) * 100 : 0;
        const color = pct >= 70 ? 'var(--color-success)' : pct >= 50 ? 'var(--color-warning)' : 'var(--color-error)';
        const name = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

        return (
          <div key={key} className="rounded-md border border-[var(--border-subtle)] overflow-hidden">
            {/* Header — always visible */}
            <button
              onClick={() => toggleDimension(key)}
              className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-[var(--interactive-secondary)] transition-colors"
            >
              {isOpen ? (
                <ChevronDown className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" />
              )}
              <span className="text-xs font-medium text-[var(--text-primary)] flex-1 truncate">
                {name}
              </span>
              {/* Progress bar */}
              <div className="w-20 h-1.5 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${pct}%`, backgroundColor: color }}
                />
              </div>
              <span className="text-xs font-mono font-bold shrink-0 w-12 text-right" style={{ color }}>
                {dim.score}/{dim.maxScore}
              </span>
            </button>

            {/* Detail — expanded */}
            {isOpen && (
              <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 space-y-3">
                {/* Critique */}
                {dim.critique && (
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                    {dim.critique}
                  </p>
                )}

                {/* Per-check rows */}
                {dim.checks.length > 0 && (
                  <div className="space-y-1.5">
                    {dim.checks.map((check, i) => {
                      const checkPct = check.maxPoints > 0 ? check.pointsAwarded / check.maxPoints : 0;
                      const checkIcon =
                        checkPct >= 1 ? <Check className="h-3 w-3 text-emerald-400" /> :
                        checkPct > 0 ? <Minus className="h-3 w-3 text-amber-400" /> :
                        <X className="h-3 w-3 text-red-400" />;

                      return (
                        <div key={i} className="flex items-start gap-2">
                          <span className="mt-0.5 shrink-0">{checkIcon}</span>
                          <div className="flex-1 min-w-0">
                            <div className="text-xs text-[var(--text-primary)]">{check.name}</div>
                            {check.evidence && (
                              <p className="text-[11px] text-[var(--text-muted)] italic mt-0.5 leading-relaxed">
                                {check.evidence}
                              </p>
                            )}
                          </div>
                          <span className="text-xs font-mono text-[var(--text-secondary)] shrink-0">
                            {check.pointsAwarded}/{check.maxPoints}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* Total bar */}
      <div className="flex items-center justify-between rounded-md border border-[var(--color-brand-accent)]/30 bg-[var(--color-brand-accent)]/5 px-3 py-2.5 mt-3">
        <span className="text-xs font-semibold text-[var(--text-primary)]">Total Score</span>
        <span className="text-sm font-bold text-[var(--text-brand)]">
          {overallScore !== null ? `${overallScore} / 100` : '—'}
        </span>
      </div>
    </div>
  );
}
