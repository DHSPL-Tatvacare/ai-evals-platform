import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { AlertTriangle, FileText, Info } from 'lucide-react';
import { Button, LoadingState, PageSurface, Tabs, Tooltip, EmptyState } from '@/components/ui';
import { PAGE_METADATA } from '@/config/pageMetadata';
import { useAppConfig } from '@/hooks';
import { CallResultPanel } from '../components/CallResultPanel';
import { NewInsideSalesEvalOverlay } from '../components/NewInsideSalesEvalOverlay';
import { MqlScoreBadge } from '../components/MqlScoreBadge';
import { LeadCallTimeline } from '../components/LeadCallTimeline';
import { fetchLeadDetail } from '@/services/api/insideSales';
import type { LeadDetailFullResponse, LeadEvalHistoryEntry } from '@/services/api/insideSales';
import type { AppDrilldownFieldConfig, AppDrilldownSectionConfig, ThreadEvalRow } from '@/types';
import { cn } from '@/utils';
import { formatFrt } from '@/utils/formatters';
import { routes } from '@/config/routes';
import { StageBadge } from '../components/StageBadge';

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
    return d.toLocaleString('en-IN', {
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

function clean(val: string | null | undefined): string {
  if (!val) return '—';
  return val.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).trim() || '—';
}

function KpiTile({ label, value, sub, valueClass }: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] px-4 py-3">
      <span className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{label}</span>
      <span className={cn('text-sm font-semibold text-[var(--text-primary)]', valueClass)}>{value}</span>
      {sub && <span className="text-[10px] text-[var(--text-muted)]">{sub}</span>}
    </div>
  );
}

function ProfileField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{label}</span>
      <span className={cn('text-xs text-[var(--text-primary)]', mono && 'font-mono')}>{value}</span>
    </div>
  );
}

function formatLeadFieldValue(lead: LeadDetailFullResponse, field: AppDrilldownFieldConfig): string {
  switch (field.key) {
    case 'phone':
      return lead.phone;
    case 'email':
      return lead.email ?? '—';
    case 'city':
      return lead.city ?? '—';
    case 'ageGroup':
      return lead.ageGroup ?? '—';
    case 'source':
      return [lead.source, lead.sourceCampaign].filter(Boolean).join(' · ') || '—';
    case 'agentName':
      return lead.agentName ?? '—';
    case 'createdOn':
      return fmtDateTime(lead.createdOn);
    case 'condition':
      return clean(lead.condition);
    case 'hba1cBand':
      return clean(lead.hba1cBand);
    case 'bloodSugarBand':
      return clean(lead.bloodSugarBand);
    case 'diabetesDuration':
      return clean(lead.diabetesDuration);
    case 'currentManagement':
      return clean(lead.currentManagement);
    case 'goal':
      return clean(lead.goal);
    case 'intentToPay':
      return clean(lead.intentToPay);
    case 'preferredCallTime':
      return lead.preferredCallTime ? fmtDateTime(lead.preferredCallTime) : '—';
    default: {
      const value = lead[field.key as keyof LeadDetailFullResponse];
      return typeof value === 'string' && value.trim() ? value : '—';
    }
  }
}

function DrilldownSectionCard({
  lead,
  section,
}: {
  lead: LeadDetailFullResponse;
  section: AppDrilldownSectionConfig;
}) {
  return (
    <section className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
      <div className="mb-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          {section.title}
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {section.fields.map((field) => (
          <ProfileField
            key={field.key}
            label={field.label}
            value={formatLeadFieldValue(lead, field)}
            mono={field.presentation === 'mono'}
          />
        ))}
      </div>
    </section>
  );
}

export function InsideSalesLeadDetail() {
  const appConfig = useAppConfig('inside-sales');
  const drilldownSections = appConfig.collections.drilldowns.lead?.sections ?? [];
  const { prospectId } = useParams<{ prospectId: string }>();

  const [lead, setLead] = useState<LeadDetailFullResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [evalIdx, setEvalIdx] = useState(0);
  const [evalOpen, setEvalOpen] = useState(false);

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
      <PageSurface
        icon={PAGE_METADATA.leadDetail.icon}
        title="Lead"
        back={{ to: routes.insideSales.listing, label: 'Leads' }}
        showHeader={false}
      >
        <LoadingState />
      </PageSurface>
    );
  }

  if (error || !lead) {
    return (
      <PageSurface
        icon={PAGE_METADATA.leadDetail.icon}
        title="Lead"
        back={{ to: routes.insideSales.listing, label: 'Leads' }}
      >
        <EmptyState
          icon={AlertTriangle}
          title="Failed to load lead"
          description={error ?? 'Lead not found.'}
          action={{ label: 'Retry', onClick: load }}
          fill
        />
      </PageSurface>
    );
  }

  const displayName = [lead.firstName, lead.lastName].filter(Boolean).join(' ') || lead.phone;
  const secondaryInfo = [lead.phone, lead.city, lead.condition].filter(Boolean).join(' · ');

  const frt = formatFrt(lead.frtSeconds);
  const tile5 = lead.preferredCallTime
    ? { label: 'Callback Adherence', value: fmtAdherence(lead.callbackAdherenceSeconds) }
    : { label: 'Lead Age', value: `${lead.leadAgeDays}d` };

  const evaluatableCall = [...lead.callHistory].find((call) => call.recordingUrl && call.evalScore === null);
  const canEvaluate = Boolean(evaluatableCall);

  const evalHistory: LeadEvalHistoryEntry[] = lead.evalHistory;
  const currentEval: LeadEvalHistoryEntry | null = evalHistory[evalIdx] ?? null;
  const activeEvalActivityId = currentEval?.threadId ?? null;

  const timelineTab = (
    <div className="space-y-3">
      {lead.historyTruncated && (
        <div className="rounded-md border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-400">
          Showing the first 200 calls — call history may be incomplete. Metrics marked with a warning may be inaccurate.
        </div>
      )}
      <LeadCallTimeline callHistory={lead.callHistory} activeEvalActivityId={activeEvalActivityId} />
    </div>
  );

  const evaluationsTab = evalHistory.length === 0 ? (
    <EmptyState
      icon={FileText}
      title="Not yet evaluated"
      description="Select a call from the timeline and click Evaluate."
      fill
    />
  ) : (
    <div className="flex flex-col gap-3">
      {evalHistory.length > 1 && (
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <button
            onClick={() => setEvalIdx((index) => Math.min(index + 1, evalHistory.length - 1))}
            disabled={evalIdx >= evalHistory.length - 1}
            className="rounded p-1 hover:bg-[var(--interactive-secondary)] disabled:opacity-40"
          >
            ‹
          </button>
          <span>Evaluation {evalHistory.length - evalIdx} of {evalHistory.length}</span>
          <button
            onClick={() => setEvalIdx((index) => Math.max(index - 1, 0))}
            disabled={evalIdx <= 0}
            className="rounded p-1 hover:bg-[var(--interactive-secondary)] disabled:opacity-40"
          >
            ›
          </button>
        </div>
      )}
      <CallResultPanel thread={currentEval as unknown as ThreadEvalRow} appId="inside-sales" />
    </div>
  );

  const metaTooltip = secondaryInfo ? (
    <div className="text-xs text-[var(--text-secondary)]">{secondaryInfo}</div>
  ) : null;

  const subtitle = (
    <>
      <StageBadge stage={lead.prospectStage} truncate={false} />
      <MqlScoreBadge score={lead.mqlScore} signals={lead.mqlSignals} />
      {metaTooltip && (
        <Tooltip content={metaTooltip} closeDelay={150}>
          <Info className="h-3.5 w-3.5 text-[var(--text-muted)] cursor-help" />
        </Tooltip>
      )}
    </>
  );

  const actions = (
    <span title={canEvaluate ? undefined : 'No unevaluated recordings'}>
      <Button size="sm" disabled={!canEvaluate} onClick={() => setEvalOpen(true)}>
        Evaluate
      </Button>
    </span>
  );

  return (
    <PageSurface
      icon={PAGE_METADATA.leadDetail.icon}
      title={displayName}
      subtitle={subtitle}
      back={{ to: routes.insideSales.listing, label: 'Leads' }}
      actions={actions}
    >
      <div className="flex flex-1 min-h-0 flex-col overflow-y-auto">
        <div className="flex flex-col gap-4 pb-4">
          <div className="grid gap-4 lg:grid-cols-2">
            {drilldownSections.map((section) => (
              <DrilldownSectionCard key={section.id} lead={lead} section={section} />
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
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

          <Tabs
            tabs={[
              { id: 'timeline', label: 'Call Timeline', content: timelineTab },
              { id: 'evaluations', label: 'Evaluations', content: evaluationsTab },
            ]}
            defaultTab="timeline"
          />
        </div>
      </div>

      {evalOpen && evaluatableCall && (
        <NewInsideSalesEvalOverlay
          onClose={() => { setEvalOpen(false); load(); }}
          preSelectedCallIds={[evaluatableCall.activityId]}
        />
      )}
    </PageSurface>
  );
}
