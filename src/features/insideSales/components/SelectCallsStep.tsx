/**
 * SelectCallsStep — wizard step 2 for inside-sales eval wizard.
 * Fetches call data from LSQ API, allows filtering and selection mode.
 */

import { useEffect, useState, useCallback } from 'react';
import { Info } from 'lucide-react';
import { apiRequest } from '@/services/api/client';
import type { CallRecord } from '@/stores/insideSalesStore';
import { formatDuration } from '@/utils/formatters';
import { cn } from '@/utils';

export interface CallSelectionConfig {
  dateFrom: string;
  dateTo: string;
  agent: string;
  direction: string;
  status: string;
  selectionMode: 'all' | 'sample' | 'specific';
  sampleSize: number;
  selectedCallIds: string[];
  skipEvaluated: boolean;
  minDuration: boolean;
}

interface SelectCallsStepProps {
  config: CallSelectionConfig;
  onConfigChange: (updates: Partial<CallSelectionConfig>) => void;
  previewCalls: CallRecord[];
  matchingCount: number;
  onPreviewLoaded: (calls: CallRecord[], total: number) => void;
}

export function SelectCallsStep({
  config,
  onConfigChange,
  previewCalls,
  matchingCount,
  onPreviewLoaded,
}: SelectCallsStepProps) {
  const [isLoading, setIsLoading] = useState(false);

  const fetchPreview = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams({
        date_from: config.dateFrom,
        date_to: config.dateTo,
        page: '1',
        page_size: '5',
      });
      if (config.agent) params.set('agent', config.agent);
      if (config.direction) params.set('direction', config.direction);
      if (config.status) params.set('status', config.status);

      const data = await apiRequest<{ calls: CallRecord[]; total: number }>(
        `/api/inside-sales/calls?${params.toString()}`
      );
      onPreviewLoaded(data.calls, data.total);
    } catch {
      onPreviewLoaded([], 0);
    } finally {
      setIsLoading(false);
    }
  }, [config.dateFrom, config.dateTo, config.agent, config.direction, config.status, onPreviewLoaded]);

  useEffect(() => {
    const timer = setTimeout(fetchPreview, 300);
    return () => clearTimeout(timer);
  }, [fetchPreview]);

  const filteredCount = config.minDuration
    ? Math.round(matchingCount * 0.85) // estimate
    : matchingCount;

  return (
    <div className="space-y-5">
      {/* Info callout */}
      <div className="flex items-start gap-2.5 rounded-md border border-blue-500/20 bg-blue-500/5 px-3 py-2.5">
        <Info className="h-4 w-4 text-blue-400 mt-0.5 shrink-0" />
        <p className="text-xs text-[var(--text-secondary)]">
          Calls are fetched live from LeadSquared. Select a date range and filters to find calls to evaluate.
        </p>
      </div>

      {/* Date range */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-[var(--text-secondary)]">Date Range</label>
        <div className="flex gap-2">
          <input
            type="date"
            value={config.dateFrom.split(' ')[0]}
            onChange={(e) => onConfigChange({ dateFrom: e.target.value + ' 00:00:00' })}
            className="flex-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
          />
          <input
            type="date"
            value={config.dateTo.split(' ')[0]}
            onChange={(e) => onConfigChange({ dateTo: e.target.value + ' 23:59:59' })}
            className="flex-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
          />
        </div>
      </div>

      {/* Agent + Direction + Status */}
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-[var(--text-secondary)]">Agent</label>
          <input
            value={config.agent}
            onChange={(e) => onConfigChange({ agent: e.target.value })}
            placeholder="All agents"
            className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-[var(--text-secondary)]">Direction</label>
          <select
            value={config.direction}
            onChange={(e) => onConfigChange({ direction: e.target.value })}
            className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
          >
            <option value="">All</option>
            <option value="inbound">Inbound</option>
            <option value="outbound">Outbound</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-[var(--text-secondary)]">Status</label>
          <select
            value={config.status}
            onChange={(e) => onConfigChange({ status: e.target.value })}
            className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
          >
            <option value="">All</option>
            <option value="answered">Answered</option>
            <option value="notanswered">Missed</option>
          </select>
        </div>
      </div>

      {/* Selection mode */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-[var(--text-secondary)]">Selection Mode</label>
        <div className="flex gap-2">
          {(['all', 'sample', 'specific'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => onConfigChange({ selectionMode: mode })}
              className={cn(
                'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                config.selectionMode === mode
                  ? 'bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]'
                  : 'bg-[var(--interactive-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              )}
            >
              {mode === 'all' ? 'All Matching' : mode === 'sample' ? 'Random Sample' : 'Specific Calls'}
            </button>
          ))}
        </div>
        {config.selectionMode === 'sample' && (
          <div className="flex items-center gap-2 mt-1">
            <label className="text-xs text-[var(--text-muted)]">Sample size:</label>
            <input
              type="number"
              value={config.sampleSize}
              onChange={(e) => onConfigChange({ sampleSize: parseInt(e.target.value, 10) || 10 })}
              className="w-20 rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2 py-1 text-xs text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
            />
          </div>
        )}
      </div>

      {/* Toggles */}
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={config.skipEvaluated}
            onChange={(e) => onConfigChange({ skipEvaluated: e.target.checked })}
            className="h-3.5 w-3.5 rounded accent-[var(--color-brand-accent)]"
          />
          Skip previously evaluated calls
        </label>
        <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={config.minDuration}
            onChange={(e) => onConfigChange({ minDuration: e.target.checked })}
            className="h-3.5 w-3.5 rounded accent-[var(--color-brand-accent)]"
          />
          Minimum duration ≥ 10 seconds
        </label>
      </div>

      {/* Stats */}
      <div className="flex gap-4 text-xs">
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[10px] font-medium text-[var(--text-muted)] uppercase">Matching</div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">
            {isLoading ? '...' : matchingCount}
          </div>
        </div>
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[10px] font-medium text-[var(--text-muted)] uppercase">After Filters</div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">
            {isLoading ? '...' : filteredCount}
          </div>
        </div>
        <div className="rounded-md border border-[var(--border-brand)]/30 bg-[var(--color-brand-accent)]/5 px-3 py-2">
          <div className="text-[10px] font-medium text-[var(--text-brand)] uppercase">To Evaluate</div>
          <div className="text-sm font-semibold text-[var(--text-brand)]">
            {isLoading ? '...' : config.selectionMode === 'sample' ? Math.min(config.sampleSize, filteredCount) : filteredCount}
          </div>
        </div>
      </div>

      {/* Preview table */}
      {previewCalls.length > 0 && (
        <div className="space-y-1.5">
          <h4 className="text-xs font-medium text-[var(--text-secondary)]">Preview (first 5)</h4>
          <div className="rounded-md border border-[var(--border-default)] overflow-hidden">
            <table className="w-full text-[11px]">
              <thead className="bg-[var(--bg-secondary)]">
                <tr>
                  <th className="px-2 py-1.5 text-left font-medium text-[var(--text-muted)]">Agent</th>
                  <th className="px-2 py-1.5 text-left font-medium text-[var(--text-muted)]">Lead</th>
                  <th className="px-2 py-1.5 text-left font-medium text-[var(--text-muted)]">Duration</th>
                  <th className="px-2 py-1.5 text-left font-medium text-[var(--text-muted)]">Status</th>
                </tr>
              </thead>
              <tbody>
                {previewCalls.map((c) => (
                  <tr key={c.activityId} className="border-t border-[var(--border-subtle)]">
                    <td className="px-2 py-1.5 text-[var(--text-primary)]">{c.agentName || '—'}</td>
                    <td className="px-2 py-1.5 text-[var(--text-primary)]">{c.leadName || '—'}</td>
                    <td className="px-2 py-1.5 text-[var(--text-secondary)]">{c.durationSeconds > 0 ? formatDuration(c.durationSeconds) : '—'}</td>
                    <td className="px-2 py-1.5 text-[var(--text-secondary)]">{c.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
