import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, AlertTriangle, FileText } from 'lucide-react';
import { Button, Tabs, EmptyState } from '@/components/ui';
import { CallResultPanel } from '../components/CallResultPanel';
import { MqlScoreBadge } from '../components/MqlScoreBadge';
import { LeadCallTimeline } from '../components/LeadCallTimeline';
import { fetchLeadDetail } from '@/services/api/insideSales';
import type { LeadDetailFullResponse, LeadEvalHistoryEntry } from '@/services/api/insideSales';
import type { ThreadEvalRow } from '@/types';
import { cn } from '@/utils';
import { routes } from '@/config/routes';

// ── Formatting helpers ────────────────────────────────────────────────────

function fmtFrt(seconds: number | null): { text: string; color: string } {
  if (seconds === null) return { text: '—', color: '' };
  if (seconds <= 3600) {
    const m = Math.floor(seconds / 60);
    return { text: m < 1 ? `${seconds}s` : `${m}m`, color: 'text-emerald-400' };
  }
  if (seconds <= 10800) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return { text: m > 0 ? `${h}h ${m}m` : `${h}h`, color: 'text-amber-400' };
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return { text: m > 0 ? `${h}h ${m}m` : `${h}h`, color: 'text-red-400' };
}

function fmtAdherence(seconds: number | null): string {
  if (seconds === null) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m after preferred time`;
  return `${m}m after preferred time`;
}

function fmtDateTime(dateStr: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr.replace(' ', 'T') + 'Z');
    return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true });
  } catch { return dateStr; }
}

function clean(val: string | null | undefined): string {
  if (!val) return '—';
  return val.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).trim() || '—';
}

// ── Stage badge ────────────────────────────────────────────────────────────

const STAGE_COLORS: Record<string, string> = {
  'new lead': 'bg-[var(--bg-secondary)] text-[var(--text-muted)]',
  'call back': 'bg-amber-500/15 text-amber-400',
  'rnr': 'bg-orange-500/15 text-orange-400',
  'interested in future plan': 'bg-blue-500/15 text-blue-400',
  'not interested': 'bg-red-500/15 text-red-400',
  'converted': 'bg-emerald-500/15 text-emerald-400',
  'invalid / junk': 'bg-[var(--bg-secondary)] text-[var(--text-muted)]',
  're-enquired': 'bg-purple-500/15 text-purple-400',
};

function StageBadge({ stage }: { stage: string }) {
  const colorClass = STAGE_COLORS[stage.toLowerCase()] ?? 'bg-[var(--bg-secondary)] text-[var(--text-muted)]';
  return <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium', colorClass)}>{stage}</span>;
}

// ── KPI Tile ──────────────────────────────────────────────────────────────

function KpiTile({ label, value, sub, valueClass }: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] px-4 py-3 flex-1 min-w-0">
      <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wide">{label}</span>
      <span className={cn('text-sm font-semibold text-[var(--text-primary)]', valueClass)}>{value}</span>
      {sub && <span className="text-[10px] text-[var(--text-muted)]">{sub}</span>}
    </div>
  );
}

// ── Profile field row ─────────────────────────────────────────────────────

function ProfileField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wide">{label}</span>
      <span className={cn('text-xs text-[var(--text-primary)]', mono && 'font-mono')}>{value}</span>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────

export function InsideSalesLeadDetail() {
  const { prospectId } = useParams<{ prospectId: string }>();
  const navigate = useNavigate();

  const [lead, setLead] = useState<LeadDetailFullResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [evalIdx, setEvalIdx] = useState(0);

  const load = useCallback(async () => {
    if (!prospectId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLeadDetail(prospectId);
      setLead(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load lead');
    } finally {
      setLoading(false);
    }
  }, [prospectId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setEvalIdx(0); }, [prospectId]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--border-default)] border-t-[var(--color-brand-accent)]" />
      </div>
    );
  }

  if (error || !lead) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <EmptyState icon={AlertTriangle} title="Failed to load lead" description={error ?? 'Lead not found.'} action={{ label: 'Retry', onClick: load }} />
      </div>
    );
  }

  const displayName = [lead.firstName, lead.lastName].filter(Boolean).join(' ') || lead.phone;
  const subtitle = [lead.phone, lead.city, lead.condition].filter(Boolean).join(' · ');

  const frt = fmtFrt(lead.frtSeconds);
  const tile5 = lead.preferredCallTime
    ? { label: 'Callback Adherence', value: fmtAdherence(lead.callbackAdherenceSeconds) }
    : { label: 'Lead Age', value: `${lead.leadAgeDays}d` };

  const evaluatableCall = [...lead.callHistory].find((c) => c.recordingUrl && c.evalScore === null);
  const canEvaluate = Boolean(evaluatableCall);

  const evalHistory: LeadEvalHistoryEntry[] = lead.evalHistory;
  const currentEval: LeadEvalHistoryEntry | null = evalHistory[evalIdx] ?? null;
  const activeEvalActivityId = currentEval?.threadId ?? null;

  const timelineTab = (
    <>
      {lead.historyTruncated && (
        <div className="mb-3 rounded-md bg-amber-500/10 border border-amber-500/20 px-3 py-2 text-[11px] text-amber-400">
          Showing the first 200 calls — call history may be incomplete. Metrics marked with a warning may be inaccurate.
        </div>
      )}
      <LeadCallTimeline callHistory={lead.callHistory} activeEvalActivityId={activeEvalActivityId} />
    </>
  );

  const evaluationsTab = (
    evalHistory.length === 0 ? (
      <div className="flex flex-1 items-center justify-center">
        <EmptyState icon={FileText} title="Not yet evaluated"
          description="Select a call from the timeline and click Evaluate." />
      </div>
    ) : (
      <div className="flex flex-col gap-3">
        {evalHistory.length > 1 && (
          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            <button onClick={() => setEvalIdx((i) => Math.min(i + 1, evalHistory.length - 1))}
              disabled={evalIdx >= evalHistory.length - 1}
              className="p-1 rounded hover:bg-[var(--interactive-secondary)] disabled:opacity-40">‹</button>
            <span>Evaluation {evalHistory.length - evalIdx} of {evalHistory.length}</span>
            <button onClick={() => setEvalIdx((i) => Math.max(i - 1, 0))}
              disabled={evalIdx <= 0}
              className="p-1 rounded hover:bg-[var(--interactive-secondary)] disabled:opacity-40">›</button>
          </div>
        )}
        <CallResultPanel thread={currentEval as unknown as ThreadEvalRow} appId="inside-sales" />
      </div>
    )
  );

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-4">
      {/* Back nav */}
      <button onClick={() => navigate(routes.insideSales.listing)}
        className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors w-fit">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Leads
      </button>

      {/* Page header */}
      <div className="flex items-start justify-between gap-4 shrink-0">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-[var(--text-primary)]">{displayName}</h1>
            <StageBadge stage={lead.prospectStage} />
            <MqlScoreBadge score={lead.mqlScore} signals={lead.mqlSignals} />
          </div>
          <p className="text-xs text-[var(--text-muted)]">{subtitle}</p>
        </div>
        <span title={canEvaluate ? undefined : 'No unevaluated recordings'}>
          <Button size="sm" disabled={!canEvaluate}>Evaluate</Button>
        </span>
      </div>

      {/* Profile card */}
      <div className="grid grid-cols-2 gap-6 rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4 shrink-0">
        <div className="space-y-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Contact & Source</p>
          <ProfileField label="Phone" value={lead.phone} mono />
          <ProfileField label="Email" value={lead.email ?? '—'} />
          <ProfileField label="City" value={lead.city ?? '—'} />
          <ProfileField label="Age Group" value={lead.ageGroup ?? '—'} />
          <ProfileField label="Source" value={[lead.source, lead.sourceCampaign].filter(Boolean).join(' · ') || '—'} />
          <ProfileField label="Agent" value={lead.agentName ?? '—'} />
          <ProfileField label="Lead Created" value={fmtDateTime(lead.createdOn)} />
        </div>
        <div className="space-y-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Health Profile</p>
          <ProfileField label="Condition" value={clean(lead.condition)} />
          <ProfileField label="HbA1c" value={clean(lead.hba1cBand)} />
          <ProfileField label="Blood Sugar" value={clean(lead.bloodSugarBand)} />
          <ProfileField label="Diabetes Duration" value={clean(lead.diabetesDuration)} />
          <ProfileField label="Current Management" value={clean(lead.currentManagement)} />
          <ProfileField label="Goal" value={clean(lead.goal)} />
          <ProfileField label="Intent to Pay" value={clean(lead.intentToPay)} />
          <ProfileField label="Preferred Call Time" value={lead.preferredCallTime ? fmtDateTime(lead.preferredCallTime) : '—'} />
        </div>
      </div>

      {/* KPI strip */}
      <div className="flex gap-3 shrink-0">
        <KpiTile label="FRT" value={frt.text} sub="SLA: 1h" valueClass={frt.color} />
        <KpiTile label="Total Dials" value={String(lead.totalDials)} />
        <KpiTile label="Connect Rate" value={lead.connectRate !== null ? `${Math.round(lead.connectRate)}%` : '—'} />
        <KpiTile
          label="Counseling"
          value={lead.historyTruncated ? '?' : String(lead.counselingCount)}
          sub={lead.historyTruncated ? 'History incomplete' : 'calls ≥ 10 min'}
        />
        <KpiTile label={tile5.label} value={tile5.value} />
      </div>

      {/* Tabs */}
      <Tabs
        tabs={[
          { id: 'timeline', label: 'Call Timeline', content: timelineTab },
          { id: 'evaluations', label: 'Evaluations', content: evaluationsTab },
        ]}
        defaultTab="timeline"
        fillHeight
      />
    </div>
  );
}
