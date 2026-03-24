/**
 * SelectCallsStep — wizard step 2 for inside-sales eval wizard.
 * Mirrors ThreadScopeStep from Kaira batch eval: radio selection modes,
 * validated sample size, specific-call multi-select with search.
 */

import { useEffect, useState, useMemo, useCallback } from 'react';
import { Search, Check, Info } from 'lucide-react';
import { apiRequest } from '@/services/api/client';
import { Input } from '@/components/ui';
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

const SCOPE_OPTIONS: { value: CallSelectionConfig['selectionMode']; label: string; description: string }[] = [
  { value: 'all', label: 'All calls', description: 'Evaluate every call matching the filters' },
  { value: 'sample', label: 'Random sample', description: 'Evaluate a random subset of matching calls' },
  { value: 'specific', label: 'Specific calls', description: 'Select individual calls to evaluate' },
];

export function SelectCallsStep({
  config,
  onConfigChange,
  matchingCount,
  onPreviewLoaded,
}: SelectCallsStepProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [allCalls, setAllCalls] = useState<CallRecord[]>([]);
  const [callSearch, setCallSearch] = useState('');
  const [sampleSizeLocal, setSampleSizeLocal] = useState<string | null>(null);
  const [sampleSizeError, setSampleSizeError] = useState('');

  // Fetch preview (first 5) for stats + preview table
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

  // Fetch all calls when "specific" mode is selected (for the multi-select list)
  useEffect(() => {
    if (config.selectionMode !== 'specific') return;

    let cancelled = false;
    (async () => {
      try {
        const params = new URLSearchParams({
          date_from: config.dateFrom,
          date_to: config.dateTo,
          page: '1',
          page_size: '100',
        });
        if (config.agent) params.set('agent', config.agent);
        if (config.direction) params.set('direction', config.direction);
        if (config.status) params.set('status', config.status);

        const data = await apiRequest<{ calls: CallRecord[]; total: number }>(
          `/api/inside-sales/calls?${params.toString()}`
        );
        if (!cancelled) setAllCalls(data.calls);
      } catch {
        if (!cancelled) setAllCalls([]);
      }
    })();
    return () => { cancelled = true; };
  }, [config.selectionMode, config.dateFrom, config.dateTo, config.agent, config.direction, config.status]);

  // Filtered call list for specific mode search
  const filteredCalls = useMemo(() => {
    if (!callSearch) return allCalls;
    const q = callSearch.toLowerCase();
    return allCalls.filter(
      (c) =>
        c.agentName.toLowerCase().includes(q) ||
        c.leadName.toLowerCase().includes(q) ||
        c.phoneNumber.includes(q) ||
        c.activityId.toLowerCase().includes(q)
    );
  }, [allCalls, callSearch]);

  const toggleCall = (activityId: string) => {
    const ids = config.selectedCallIds;
    if (ids.includes(activityId)) {
      onConfigChange({ selectedCallIds: ids.filter((id) => id !== activityId) });
    } else {
      onConfigChange({ selectedCallIds: [...ids, activityId] });
    }
  };

  const toggleAll = () => {
    const filteredIds = filteredCalls.map((c) => c.activityId);
    if (config.selectedCallIds.length === filteredIds.length) {
      onConfigChange({ selectedCallIds: [] });
    } else {
      onConfigChange({ selectedCallIds: [...filteredIds] });
    }
  };

  const callLabel = (c: CallRecord) => {
    const name = c.leadName || c.phoneNumber || c.activityId.slice(0, 8);
    const agent = c.agentName || '—';
    const dur = c.durationSeconds > 0 ? formatDuration(c.durationSeconds) : '—';
    return { name, agent, dur, status: c.status || '—' };
  };

  return (
    <div className="space-y-4">
      {/* Info callout */}
      <div className="flex items-start gap-2.5 rounded-md border border-blue-500/20 bg-blue-500/5 px-3 py-2.5">
        <Info className="h-4 w-4 text-blue-400 mt-0.5 shrink-0" />
        <p className="text-[12px] text-[var(--text-secondary)]">
          Calls are fetched live from LeadSquared. Select a date range and filters to find calls to evaluate.
        </p>
      </div>

      {/* Date range */}
      <div className="space-y-1.5">
        <label className="block text-[13px] font-medium text-[var(--text-primary)]">Date Range</label>
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
          <label className="text-[13px] font-medium text-[var(--text-primary)]">Agent</label>
          <input
            value={config.agent}
            onChange={(e) => onConfigChange({ agent: e.target.value })}
            placeholder="All agents"
            className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-[13px] font-medium text-[var(--text-primary)]">Direction</label>
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
          <label className="text-[13px] font-medium text-[var(--text-primary)]">Status</label>
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

      {/* Call Selection — radio group (mirrors ThreadScopeStep) */}
      <div>
        <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-2">
          Call Selection
        </label>
        <div className="space-y-2">
          {SCOPE_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={cn(
                'flex items-start gap-3 px-3 py-2.5 rounded-[6px] border cursor-pointer transition-colors',
                config.selectionMode === opt.value
                  ? 'border-[var(--interactive-primary)] bg-[var(--color-brand-accent)]/5'
                  : 'border-[var(--border-subtle)] bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)]'
              )}
            >
              <input
                type="radio"
                name="callScope"
                value={opt.value}
                checked={config.selectionMode === opt.value}
                onChange={() => onConfigChange({ selectionMode: opt.value })}
                className="mt-0.5 accent-[var(--interactive-primary)]"
              />
              <div>
                <span className="text-[13px] font-medium text-[var(--text-primary)]">{opt.label}</span>
                <p className="text-[11px] text-[var(--text-muted)]">{opt.description}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Sample size input */}
      {config.selectionMode === 'sample' && (
        <div>
          <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
            Sample Size
          </label>
          <Input
            type="number"
            min={1}
            max={matchingCount}
            value={sampleSizeLocal ?? String(config.sampleSize)}
            error={sampleSizeError}
            onFocus={() => setSampleSizeLocal(String(config.sampleSize))}
            onChange={(e) => {
              const raw = e.target.value;
              setSampleSizeLocal(raw);
              const parsed = parseInt(raw);
              if (raw === '' || isNaN(parsed)) {
                setSampleSizeError('');
              } else if (parsed < 1) {
                setSampleSizeError('Minimum is 1');
              } else if (parsed > matchingCount) {
                setSampleSizeError(`Maximum is ${matchingCount}`);
              } else {
                setSampleSizeError('');
                onConfigChange({ sampleSize: parsed });
              }
            }}
            onBlur={() => {
              const parsed = parseInt(sampleSizeLocal ?? '');
              if (isNaN(parsed) || parsed < 1) {
                // Reset to last valid value
              } else if (parsed > matchingCount) {
                onConfigChange({ sampleSize: matchingCount });
              }
              setSampleSizeError('');
              setSampleSizeLocal(null);
            }}
          />
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">
            {isLoading ? '...' : `${matchingCount} calls available`}
          </p>
        </div>
      )}

      {/* Specific call multi-select */}
      {config.selectionMode === 'specific' && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-[13px] font-medium text-[var(--text-primary)]">
              Select Calls
            </label>
            <span className="text-[11px] text-[var(--text-muted)]">
              {config.selectedCallIds.length} of {allCalls.length} selected
            </span>
          </div>

          {/* Search */}
          <Input
            icon={<Search className="h-4 w-4" />}
            value={callSearch}
            onChange={(e) => setCallSearch(e.target.value)}
            placeholder="Search by agent, lead, phone..."
            className="mb-2"
          />

          {/* Select all toggle */}
          <button
            type="button"
            onClick={toggleAll}
            className="text-[11px] text-[var(--text-brand)] hover:underline mb-1.5"
          >
            {config.selectedCallIds.length === filteredCalls.length && filteredCalls.length > 0
              ? 'Deselect all'
              : 'Select all'}
          </button>

          {/* Call list */}
          <div className="max-h-48 overflow-y-auto rounded-[6px] border border-[var(--border-subtle)]">
            {filteredCalls.length === 0 ? (
              <p className="px-3 py-4 text-center text-[13px] text-[var(--text-muted)]">
                {allCalls.length === 0 ? 'Loading calls...' : 'No calls found'}
              </p>
            ) : (
              filteredCalls.map((c) => {
                const isSelected = config.selectedCallIds.includes(c.activityId);
                const info = callLabel(c);
                return (
                  <button
                    key={c.activityId}
                    type="button"
                    onClick={() => toggleCall(c.activityId)}
                    className={cn(
                      'flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] transition-colors',
                      'hover:bg-[var(--interactive-secondary)]',
                      isSelected && 'bg-[var(--color-brand-accent)]/5'
                    )}
                  >
                    <div
                      className={cn(
                        'h-4 w-4 rounded border flex items-center justify-center shrink-0 transition-colors',
                        isSelected
                          ? 'bg-[var(--interactive-primary)] border-[var(--interactive-primary)]'
                          : 'border-[var(--border-default)] bg-[var(--bg-primary)]'
                      )}
                    >
                      {isSelected && <Check className="h-3 w-3 text-[var(--text-on-color)]" />}
                    </div>
                    <span className="text-[var(--text-primary)] truncate flex-1">{info.name}</span>
                    <span className="text-[11px] text-[var(--text-muted)] shrink-0">{info.agent}</span>
                    <span className="text-[11px] text-[var(--text-muted)] shrink-0 w-10 text-right">{info.dur}</span>
                    <span className="text-[11px] text-[var(--text-muted)] shrink-0 w-16 text-right">{info.status}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Skip previously evaluated + minimum duration */}
      <div className="border-t border-[var(--border-subtle)] pt-3 mt-1">
        <label className="flex items-start gap-3 cursor-pointer mb-2">
          <input
            type="checkbox"
            checked={config.skipEvaluated}
            onChange={(e) => onConfigChange({ skipEvaluated: e.target.checked })}
            className="mt-0.5 accent-[var(--interactive-primary)]"
          />
          <div>
            <span className="text-[13px] font-medium text-[var(--text-primary)]">
              Skip previously evaluated calls
            </span>
            <p className="text-[11px] text-[var(--text-muted)]">
              Calls already evaluated in any past run will be excluded.
              {config.selectionMode === 'sample' && ' Sampling will draw from the remaining unevaluated calls.'}
            </p>
          </div>
        </label>
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={config.minDuration}
            onChange={(e) => onConfigChange({ minDuration: e.target.checked })}
            className="mt-0.5 accent-[var(--interactive-primary)]"
          />
          <div>
            <span className="text-[13px] font-medium text-[var(--text-primary)]">
              Minimum duration ≥ 10 seconds
            </span>
            <p className="text-[11px] text-[var(--text-muted)]">
              Skip very short or failed calls with no meaningful conversation.
            </p>
          </div>
        </label>
      </div>

      {/* Stats summary */}
      <div className="flex gap-4 text-xs">
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[10px] font-medium text-[var(--text-muted)] uppercase">Matching</div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">
            {isLoading ? '...' : matchingCount}
          </div>
        </div>
        <div className="rounded-md border border-[var(--border-brand)]/30 bg-[var(--color-brand-accent)]/5 px-3 py-2">
          <div className="text-[10px] font-medium text-[var(--text-brand)] uppercase">To Evaluate</div>
          <div className="text-sm font-semibold text-[var(--text-brand)]">
            {isLoading
              ? '...'
              : config.selectionMode === 'specific'
                ? config.selectedCallIds.length
                : config.selectionMode === 'sample'
                  ? Math.min(config.sampleSize, matchingCount)
                  : matchingCount}
          </div>
        </div>
      </div>
    </div>
  );
}
