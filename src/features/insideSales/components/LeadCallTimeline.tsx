/**
 * Call Timeline tab content — table of all calls for a lead.
 */
import { Play } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/utils';
import { formatDuration } from '@/utils/formatters';
import { scoreColor } from '@/utils/scoreUtils';
import { routes } from '@/config/routes';
import type { LeadCallRecord } from '@/services/api/insideSales';

interface LeadCallTimelineProps {
  callHistory: LeadCallRecord[];
  /** activityId of the call currently shown in the Evaluations tab, for accent highlight */
  activeEvalActivityId?: string | null;
}

function formatCallDateTime(dateStr: string): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr.replace(' ', 'T') + 'Z');
    return d.toLocaleString('en-IN', {
      day: '2-digit', month: 'short',
      hour: '2-digit', minute: '2-digit', hour12: true,
    });
  } catch {
    return dateStr;
  }
}

function CallStatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const style =
    s === 'answered' ? 'bg-emerald-500/15 text-emerald-400' :
    s === 'callfailure' || s === 'call failure' ? 'bg-[var(--bg-secondary)] text-[var(--text-muted)]' :
    'bg-red-500/15 text-red-400';
  const label =
    s === 'answered' ? 'Answered' :
    s === 'callfailure' || s === 'call failure' ? 'Call Failure' :
    'Not Answered';
  return (
    <span className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium', style)}>
      {label}
    </span>
  );
}

export function LeadCallTimeline({ callHistory, activeEvalActivityId }: LeadCallTimelineProps) {
  const navigate = useNavigate();

  if (callHistory.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center py-12 text-xs text-[var(--text-muted)]">
        No call activity found.
      </div>
    );
  }

  return (
    <div className="overflow-auto rounded-md border border-[var(--border-default)]">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-[var(--bg-secondary)] z-10">
          <tr className="border-b border-[var(--border-default)]">
            <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Time</th>
            <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Agent</th>
            <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Duration</th>
            <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Status</th>
            <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Eval</th>
            <th className="w-8 px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          {callHistory.map((call) => {
            const isActive = call.activityId === activeEvalActivityId;
            return (
              <tr
                key={call.activityId}
                className={cn(
                  'border-b border-[var(--border-subtle)] transition-colors',
                  isActive && 'border-l-2 border-l-[var(--color-brand-accent)]',
                )}
              >
                <td className="px-3 py-2.5 text-[var(--text-primary)] whitespace-nowrap">
                  {formatCallDateTime(call.callTime)}
                </td>
                <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                  {call.agentName || '—'}
                </td>
                <td className={cn(
                  'px-3 py-2.5 tabular-nums whitespace-nowrap',
                  call.isCounseling ? 'font-semibold text-emerald-400' : 'text-[var(--text-secondary)]',
                )}>
                  {call.durationSeconds > 0 ? formatDuration(call.durationSeconds) : '—'}
                </td>
                <td className="px-3 py-2.5">
                  <CallStatusBadge status={call.status} />
                </td>
                <td className="px-3 py-2.5">
                  {call.evalScore !== null ? (
                    <span
                      style={{ color: scoreColor(call.evalScore) }}
                      className="text-xs font-mono font-semibold"
                    >
                      {Math.round(call.evalScore)}
                    </span>
                  ) : (
                    <span className="text-[var(--text-muted)]">—</span>
                  )}
                </td>
                <td className="w-8 px-2 py-2.5">
                  {call.recordingUrl ? (
                    <button
                      onClick={() => navigate(routes.insideSales.callView(call.activityId))}
                      className="rounded-full p-1.5 bg-[var(--color-brand-accent)]/10 text-[var(--color-brand-accent)] hover:bg-[var(--color-brand-accent)]/25 transition-colors"
                      title="Open call detail"
                    >
                      <Play className="h-3.5 w-3.5" />
                    </button>
                  ) : (
                    <span className="text-[var(--text-muted)] text-[10px]">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
