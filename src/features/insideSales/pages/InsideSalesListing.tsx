import { useEffect, useMemo, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search,
  ChevronLeft,
  ChevronRight,
  Phone,
  PhoneIncoming,
  PhoneOutgoing,
  Filter,
  X,
  Play,
  Square,
} from 'lucide-react';
import { Button, EmptyState, Tabs } from '@/components/ui';
import { useInsideSalesStore } from '@/stores';
import type { CallRecord } from '@/stores/insideSalesStore';
import { cn } from '@/utils';
import { formatDuration } from '@/utils/formatters';
import { routes } from '@/config/routes';
import { CallFilterPanel } from '../components/CallFilterPanel';

/* ── Helpers ─────────────────────────────────────────────── */

function formatCallTime(dateStr: string): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr.replace(' ', 'T') + 'Z');
    return d.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return dateStr;
  }
}

function DirectionBadge({ direction }: { direction: string }) {
  const isInbound = direction === 'inbound';
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
        isInbound
          ? 'bg-purple-500/15 text-purple-400'
          : 'bg-blue-500/15 text-blue-400'
      )}
    >
      {isInbound ? <PhoneIncoming className="h-3 w-3" /> : <PhoneOutgoing className="h-3 w-3" />}
      {isInbound ? 'In' : 'Out'}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const isAnswered = status.toLowerCase() === 'answered';
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium',
        isAnswered
          ? 'bg-emerald-500/15 text-emerald-400'
          : 'bg-red-500/15 text-red-400'
      )}
    >
      {isAnswered ? 'Answered' : 'Missed'}
    </span>
  );
}

/* ── Main Component ──────────────────────────────────────── */

export function InsideSalesListing() {
  const navigate = useNavigate();
  const calls = useInsideSalesStore((s) => s.calls);
  const total = useInsideSalesStore((s) => s.total);
  const page = useInsideSalesStore((s) => s.page);
  const pageSize = useInsideSalesStore((s) => s.pageSize);
  const isLoading = useInsideSalesStore((s) => s.isLoading);
  const error = useInsideSalesStore((s) => s.error);
  const filters = useInsideSalesStore((s) => s.filters);
  const selectedCallIds = useInsideSalesStore((s) => s.selectedCallIds);

  const [filterPanelOpen, setFilterPanelOpen] = useState(false);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [audioEl] = useState(() => typeof Audio !== 'undefined' ? new Audio() : null);

  // Load calls on mount and when page/filters change
  useEffect(() => {
    useInsideSalesStore.getState().loadCalls();
  }, [page, filters]);

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (audioEl) {
        audioEl.pause();
        audioEl.src = '';
      }
    };
  }, [audioEl]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Search filtering (client-side on already-fetched data)
  const filteredCalls = useMemo(() => {
    const q = filters.search.toLowerCase().trim();
    if (!q) return calls;
    return calls.filter(
      (c) =>
        c.agentName.toLowerCase().includes(q) ||
        c.leadName.toLowerCase().includes(q) ||
        c.phoneNumber.includes(q) ||
        c.displayNumber.includes(q)
    );
  }, [calls, filters.search]);

  // Active filter count (excluding dateFrom/dateTo/search which have dedicated UI)
  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.agent) count++;
    if (filters.direction) count++;
    if (filters.status) count++;
    if (filters.eventCodes) count++;
    if (filters.evalStatus) count++;
    if (filters.durationMin) count++;
    if (filters.durationMax) count++;
    if (filters.scoreMin) count++;
    if (filters.scoreMax) count++;
    return count;
  }, [filters]);

  const handlePageChange = useCallback((newPage: number) => {
    useInsideSalesStore.getState().setPage(newPage);
  }, []);

  const handleSearchChange = useCallback((value: string) => {
    useInsideSalesStore.getState().setFilters({ search: value });
  }, []);

  const handleRowClick = useCallback(
    (call: CallRecord) => {
      navigate(routes.insideSales.callView(call.activityId));
    },
    [navigate]
  );

  const handleToggleSelect = useCallback((activityId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    useInsideSalesStore.getState().toggleCallSelection(activityId);
  }, []);

  const handleSelectAll = useCallback(() => {
    const store = useInsideSalesStore.getState();
    if (selectedCallIds.size === filteredCalls.length) {
      store.deselectAll();
    } else {
      store.selectAllOnPage();
    }
  }, [selectedCallIds.size, filteredCalls.length]);

  const handlePlayToggle = useCallback(
    (call: CallRecord, e: React.MouseEvent) => {
      e.stopPropagation();
      if (!audioEl || !call.recordingUrl) return;

      if (playingId === call.activityId) {
        audioEl.pause();
        setPlayingId(null);
      } else {
        audioEl.src = call.recordingUrl;
        audioEl.play();
        setPlayingId(call.activityId);
        audioEl.onended = () => setPlayingId(null);
      }
    },
    [audioEl, playingId]
  );

  const handleClearFilters = useCallback(() => {
    useInsideSalesStore.getState().clearFilters();
  }, []);

  const tableContent = (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Search + filter toolbar */}
      <div className="flex items-center gap-2 py-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--text-muted)]" />
          <input
            type="text"
            value={filters.search}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search agent, lead, phone..."
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
          />
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => setFilterPanelOpen(true)}
          className="gap-1.5"
        >
          <Filter className="h-3.5 w-3.5" />
          Filters
          {activeFilterCount > 0 && (
            <span className="ml-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-[var(--color-brand-accent)] text-[10px] font-bold text-white">
              {activeFilterCount}
            </span>
          )}
        </Button>

        {activeFilterCount > 0 && (
          <button
            onClick={handleClearFilters}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            Clear all
          </button>
        )}

        <span className="ml-auto text-xs text-[var(--text-muted)]">
          {total} call{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Active filter pills */}
      {activeFilterCount > 0 && (
        <div className="flex flex-wrap gap-1.5 pb-2">
          {filters.agent && (
            <FilterPill
              label={`Agent: ${filters.agent}`}
              onRemove={() => useInsideSalesStore.getState().setFilters({ agent: '' })}
            />
          )}
          {filters.direction && (
            <FilterPill
              label={`Dir: ${filters.direction}`}
              onRemove={() => useInsideSalesStore.getState().setFilters({ direction: '' })}
            />
          )}
          {filters.status && (
            <FilterPill
              label={`Status: ${filters.status}`}
              onRemove={() => useInsideSalesStore.getState().setFilters({ status: '' })}
            />
          )}
          {filters.eventCodes && (
            <FilterPill
              label={`Events: ${filters.eventCodes}`}
              onRemove={() => useInsideSalesStore.getState().setFilters({ eventCodes: '' })}
            />
          )}
        </div>
      )}

      {/* Bulk selection bar */}
      {selectedCallIds.size > 0 && (
        <div className="flex items-center gap-3 rounded-md bg-[var(--color-brand-accent)]/10 px-3 py-2 mb-2">
          <span className="text-xs font-medium text-[var(--text-brand)]">
            {selectedCallIds.size} selected
          </span>
          <button
            onClick={() => useInsideSalesStore.getState().deselectAll()}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            Deselect all
          </button>
          <Button size="sm" className="ml-auto">
            Evaluate Selected
          </Button>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-2">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--border-default)] border-t-[var(--color-brand-accent)]" />
            <span className="text-xs text-[var(--text-muted)]">Loading calls...</span>
          </div>
        </div>
      ) : error ? (
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={Phone}
            title="Failed to load calls"
            description={error}
            action={{
              label: 'Retry',
              onClick: () => useInsideSalesStore.getState().loadCalls(),
            }}
          />
        </div>
      ) : filteredCalls.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={Phone}
            title={filters.search ? 'No matching calls' : 'No calls found'}
            description={
              filters.search
                ? 'Try adjusting your search terms.'
                : 'No call activities for the selected date range.'
            }
          />
        </div>
      ) : (
        <>
          <div className="flex-1 overflow-auto rounded-md border border-[var(--border-default)]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[var(--bg-secondary)] z-10">
                <tr className="border-b border-[var(--border-default)]">
                  <th className="w-8 px-2 py-2 text-left">
                    <input
                      type="checkbox"
                      checked={selectedCallIds.size === filteredCalls.length && filteredCalls.length > 0}
                      onChange={handleSelectAll}
                      className="h-3.5 w-3.5 rounded border-[var(--border-default)] accent-[var(--color-brand-accent)]"
                    />
                  </th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Date / Time</th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Agent</th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Lead</th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Phone</th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Duration</th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Dir</th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Status</th>
                  <th className="w-10 px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {filteredCalls.map((call) => (
                  <tr
                    key={call.activityId}
                    onClick={() => handleRowClick(call)}
                    className={cn(
                      'border-b border-[var(--border-subtle)] cursor-pointer transition-colors',
                      'hover:bg-[var(--interactive-secondary)]',
                      selectedCallIds.has(call.activityId) && 'bg-[var(--color-brand-accent)]/5'
                    )}
                  >
                    <td className="w-8 px-2 py-2.5">
                      <input
                        type="checkbox"
                        checked={selectedCallIds.has(call.activityId)}
                        onClick={(e) => handleToggleSelect(call.activityId, e)}
                        onChange={() => {}}
                        className="h-3.5 w-3.5 rounded border-[var(--border-default)] accent-[var(--color-brand-accent)]"
                      />
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-primary)] whitespace-nowrap">
                      {formatCallTime(call.callStartTime)}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-primary)] max-w-[120px] truncate">
                      {call.agentName || '—'}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-primary)] max-w-[120px] truncate">
                      {call.leadName || '—'}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-[var(--text-secondary)]">
                      {call.phoneNumber || call.displayNumber || '—'}
                    </td>
                    <td className="px-3 py-2.5 text-[var(--text-secondary)] whitespace-nowrap">
                      {call.durationSeconds > 0 ? formatDuration(call.durationSeconds) : '—'}
                    </td>
                    <td className="px-3 py-2.5">
                      <DirectionBadge direction={call.direction} />
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={call.status} />
                    </td>
                    <td className="w-10 px-2 py-2.5">
                      {call.recordingUrl && (
                        <button
                          onClick={(e) => handlePlayToggle(call, e)}
                          className="rounded-full p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--interactive-secondary)] transition-colors"
                          title={playingId === call.activityId ? 'Stop' : 'Play'}
                        >
                          {playingId === call.activityId ? (
                            <Square className="h-3.5 w-3.5" />
                          ) : (
                            <Play className="h-3.5 w-3.5" />
                          )}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between pt-3 pb-1">
            <span className="text-xs text-[var(--text-muted)]">
              Page {page} of {totalPages} · {total} calls
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => handlePageChange(page - 1)}
                className="h-7 w-7 p-0"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => handlePageChange(page + 1)}
                className="h-7 w-7 p-0"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-[calc(100vh-var(--header-height))]">
      {/* Page header */}
      <div className="flex items-center justify-between shrink-0 pb-2">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">Calls</h1>
        {selectedCallIds.size > 0 && (
          <Button size="sm">
            Evaluate Selected ({selectedCallIds.size})
          </Button>
        )}
      </div>

      {/* Tabs (single tab for now) */}
      <Tabs
        tabs={[{ id: 'all', label: 'All Calls', content: tableContent }]}
        defaultTab="all"
        fillHeight
      />

      {/* Filter panel */}
      {filterPanelOpen && (
        <CallFilterPanel onClose={() => setFilterPanelOpen(false)} />
      )}
    </div>
  );
}

/* ── Filter Pill ─────────────────────────────────────────── */

function FilterPill({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-[var(--interactive-secondary)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
      {label}
      <button
        onClick={onRemove}
        className="ml-0.5 rounded-full p-0.5 hover:bg-[var(--border-default)] transition-colors"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}
