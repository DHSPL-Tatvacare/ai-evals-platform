/**
 * Call Filter Panel — right-slide overlay for call listing filters.
 * Stub: will be fully built in Task 5.
 */

import { X } from 'lucide-react';
import { Button } from '@/components/ui';
import { useInsideSalesStore } from '@/stores';

interface CallFilterPanelProps {
  onClose: () => void;
}

export function CallFilterPanel({ onClose }: CallFilterPanelProps) {
  const filters = useInsideSalesStore((s) => s.filters);

  const handleApply = () => {
    onClose();
  };

  const handleReset = () => {
    useInsideSalesStore.getState().clearFilters();
    onClose();
  };

  const handleDateChange = (field: 'dateFrom' | 'dateTo', value: string) => {
    useInsideSalesStore.getState().setFilters({ [field]: value });
  };

  const handleFieldChange = (field: string, value: string) => {
    useInsideSalesStore.getState().setFilters({ [field]: value });
  };

  return (
    <div className="fixed inset-0 z-50" onClick={onClose}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />

      {/* Panel */}
      <div
        className="absolute top-0 right-0 bottom-0 w-[380px] bg-[var(--bg-primary)] border-l border-[var(--border-default)] shadow-xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border-default)]">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Filters</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--interactive-secondary)] transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {/* Date range */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-[var(--text-secondary)]">Date Range</label>
            <div className="flex gap-2">
              <input
                type="date"
                value={filters.dateFrom.split(' ')[0]}
                onChange={(e) => handleDateChange('dateFrom', e.target.value + ' 00:00:00')}
                className="flex-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
              />
              <input
                type="date"
                value={filters.dateTo.split(' ')[0]}
                onChange={(e) => handleDateChange('dateTo', e.target.value + ' 23:59:59')}
                className="flex-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
              />
            </div>
          </div>

          {/* Agent */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-[var(--text-secondary)]">Agent</label>
            <input
              type="text"
              value={filters.agent}
              onChange={(e) => handleFieldChange('agent', e.target.value)}
              placeholder="Filter by agent name..."
              className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
            />
          </div>

          {/* Direction */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-[var(--text-secondary)]">Direction</label>
            <div className="flex gap-2">
              {['', 'inbound', 'outbound'].map((val) => (
                <button
                  key={val}
                  onClick={() => handleFieldChange('direction', val)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    filters.direction === val
                      ? 'bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]'
                      : 'bg-[var(--interactive-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {val === '' ? 'All' : val === 'inbound' ? 'Inbound' : 'Outbound'}
                </button>
              ))}
            </div>
          </div>

          {/* Call Status */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-[var(--text-secondary)]">Call Status</label>
            <div className="flex gap-2">
              {['', 'answered', 'notanswered'].map((val) => (
                <button
                  key={val}
                  onClick={() => handleFieldChange('status', val)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    filters.status === val
                      ? 'bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]'
                      : 'bg-[var(--interactive-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {val === '' ? 'All' : val === 'answered' ? 'Answered' : 'Missed'}
                </button>
              ))}
            </div>
          </div>

          {/* Duration range */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-[var(--text-secondary)]">Duration (seconds)</label>
            <div className="flex gap-2">
              <input
                type="number"
                value={filters.durationMin}
                onChange={(e) => handleFieldChange('durationMin', e.target.value)}
                placeholder="Min"
                className="flex-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
              />
              <input
                type="number"
                value={filters.durationMax}
                onChange={(e) => handleFieldChange('durationMax', e.target.value)}
                placeholder="Max"
                className="flex-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-[var(--border-default)]">
          <Button variant="ghost" size="sm" onClick={handleReset}>
            Reset
          </Button>
          <Button size="sm" onClick={handleApply}>
            Apply
          </Button>
        </div>
      </div>
    </div>
  );
}
