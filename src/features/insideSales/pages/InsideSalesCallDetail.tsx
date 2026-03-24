import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  PhoneIncoming,
  PhoneOutgoing,
  Clock,
  User,
  Users,
  Phone as PhoneIcon,
  Calendar,
} from 'lucide-react';
import { Button, Tabs, EmptyState } from '@/components/ui';
import { AudioPlayer } from '@/features/transcript/components/AudioPlayer';
import { useInsideSalesStore } from '@/stores';
import { cn } from '@/utils';
import { formatDuration } from '@/utils/formatters';
import { routes } from '@/config/routes';

function formatDateTime(dateStr: string): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr.replace(' ', 'T') + 'Z');
    return d.toLocaleString('en-IN', {
      weekday: 'short',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return dateStr;
  }
}

export function InsideSalesCallDetail() {
  const navigate = useNavigate();
  const { activityId } = useParams<{ activityId: string }>();
  const activeCall = useInsideSalesStore((s) => s.activeCall);
  const calls = useInsideSalesStore((s) => s.calls);

  // Prefer activeCall (set on row click), fall back to searching the loaded page
  const call = useMemo(
    () => (activeCall?.activityId === activityId ? activeCall : calls.find((c) => c.activityId === activityId)) ?? null,
    [activeCall, calls, activityId]
  );

  if (!call) {
    return (
      <div className="flex flex-col flex-1 min-h-0">
        <div className="shrink-0 pb-4">
          <button
            onClick={() => navigate(routes.insideSales.listing)}
            className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to Calls
          </button>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={PhoneIcon}
            title="Call not found"
            description="This call may not be loaded. Go back to the listing and try again."
            action={{ label: 'Back to Calls', onClick: () => navigate(routes.insideSales.listing) }}
          />
        </div>
      </div>
    );
  }

  const isInbound = call.direction === 'inbound';
  const isAnswered = call.status.toLowerCase() === 'answered';

  const transcriptTab = {
    id: 'transcript',
    label: 'Transcript',
    content: (
      <div className="flex items-center justify-center py-16">
        <EmptyState
          icon={PhoneIcon}
          title="No transcript yet"
          description="Transcription will be available after evaluation."
          compact
        />
      </div>
    ),
  };

  const scorecardTab = {
    id: 'scorecard',
    label: 'Scorecard',
    content: (
      <div className="flex items-center justify-center py-16">
        <EmptyState
          icon={PhoneIcon}
          title="Not yet evaluated"
          description="Run an evaluation to see the scorecard."
          compact
        />
      </div>
    ),
  };

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-4">
      {/* Back button */}
      <div className="shrink-0">
        <button
          onClick={() => navigate(routes.insideSales.listing)}
          className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Calls
        </button>
      </div>

      {/* Header */}
      <div className="shrink-0 flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">
            {call.agentName || 'Unknown Agent'}
            {call.leadName && (
              <span className="text-[var(--text-muted)] font-normal"> → {call.leadName}</span>
            )}
          </h1>
          <div className="flex items-center gap-2 mt-1">
            <span
              className={cn(
                'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
                isInbound
                  ? 'bg-purple-500/15 text-purple-400'
                  : 'bg-blue-500/15 text-blue-400'
              )}
            >
              {isInbound ? <PhoneIncoming className="h-3 w-3" /> : <PhoneOutgoing className="h-3 w-3" />}
              {isInbound ? 'Inbound' : 'Outbound'}
            </span>
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
          </div>
        </div>
        <Button size="sm" disabled>
          Evaluate
        </Button>
      </div>

      {/* Metadata grid */}
      <div className="shrink-0 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetaCard icon={Calendar} label="Date" value={formatDateTime(call.callStartTime)} />
        <MetaCard icon={User} label="Agent" value={call.agentName || '—'} />
        <MetaCard icon={Users} label="Lead" value={call.leadName || '—'} />
        <MetaCard icon={PhoneIcon} label="Phone" value={call.phoneNumber || call.displayNumber || '—'} mono />
        <MetaCard icon={Clock} label="Duration" value={call.durationSeconds > 0 ? formatDuration(call.durationSeconds) : '—'} />
        <MetaCard icon={PhoneIcon} label="Session" value={call.callSessionId ? call.callSessionId.slice(-8) : '—'} mono />
      </div>

      {/* Audio player */}
      {call.recordingUrl && (
        <div className="shrink-0">
          <AudioPlayer audioUrl={call.recordingUrl} appId="inside-sales" />
        </div>
      )}

      {/* Tabs: Transcript + Scorecard */}
      <Tabs tabs={[transcriptTab, scorecardTab]} defaultTab="transcript" fillHeight />
    </div>
  );
}

function MetaCard({
  icon: Icon,
  label,
  value,
  mono,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[var(--text-muted)] mb-1">
        <Icon className="h-3 w-3" />
        <span className="text-[10px] font-medium uppercase tracking-wide">{label}</span>
      </div>
      <div className={cn('text-xs text-[var(--text-primary)] truncate', mono && 'font-mono')}>
        {value}
      </div>
    </div>
  );
}
