import { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  FileText,
  HeartPulse,
  Info,
  ListChecks,
  Mic,
  User,
} from 'lucide-react';
import {
  Button,
  EmptyState,
  LoadingState,
  MetricChip,
  PageSurface,
  RecordNavigator,
  RecordWorkspace,
  SectionBlock,
  Tooltip,
  type RecordWorkspaceTab,
} from '@/components/ui';
import { PAGE_METADATA } from '@/config/pageMetadata';
import { useAppConfig } from '@/hooks';
import { AudioPlayer } from '@/features/transcript/components/AudioPlayer';
import { CallResultPanel } from '../components/CallResultPanel';
import { NewInsideSalesEvalOverlay } from '../components/NewInsideSalesEvalOverlay';
import { MqlScoreBadge } from '../components/MqlScoreBadge';
import { LeadCallTimeline } from '../components/LeadCallTimeline';
import { fetchLeadDetail } from '@/services/api/insideSales';
import { useLeadsStore } from '@/stores/insideSalesStore';
import type {
  LeadCallRecord,
  LeadDetailFullResponse,
  LeadEvalHistoryEntry,
} from '@/services/api/insideSales';
import type { AppDrilldownFieldConfig, AppDrilldownSectionConfig, ThreadEvalRow } from '@/types';
import { cn } from '@/utils';
import { formatFrt } from '@/utils/formatters';
import { routes } from '@/config/routes';
import { StageBadge } from '../components/StageBadge';

/* ── Formatting helpers ───────────────────────────────────────── */

function fmtAdherence(seconds: number | null): string {
  if (seconds === null) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m after preferred`;
  return `${m}m after preferred`;
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

function cleanEnum(val: string | null | undefined): string {
  if (!val) return '—';
  return val.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).trim() || '—';
}

/* ── Small building blocks ─────────────────────────────────────── */

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </span>
      <span
        className={cn(
          'text-[13px] text-[var(--text-primary)] truncate',
          mono && 'font-mono',
        )}
        title={value !== '—' ? value : undefined}
      >
        {value}
      </span>
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
      return cleanEnum(lead.condition);
    case 'hba1cBand':
      return cleanEnum(lead.hba1cBand);
    case 'bloodSugarBand':
      return cleanEnum(lead.bloodSugarBand);
    case 'diabetesDuration':
      return cleanEnum(lead.diabetesDuration);
    case 'currentManagement':
      return cleanEnum(lead.currentManagement);
    case 'goal':
      return cleanEnum(lead.goal);
    case 'intentToPay':
      return cleanEnum(lead.intentToPay);
    case 'preferredCallTime':
      return lead.preferredCallTime ? fmtDateTime(lead.preferredCallTime) : '—';
    default: {
      const value = lead[field.key as keyof LeadDetailFullResponse];
      return typeof value === 'string' && value.trim() ? value : '—';
    }
  }
}

/* ── Plan purchase surface ─────────────────────────────────────── */

/** Order = how a sales-ops reader scans a purchase:
 *  plan → pricing → payment → program dates → device → fulfilment.
 */
const PLAN_FIELD_LABELS: Array<[keyof LeadDetailFullResponse['plan'], string]> = [
  ['planName', 'Plan Name'],
  ['durationOrQuantity', 'Duration'],
  ['programPrice', 'Program Price'],
  ['invoiceAmount', 'Invoice Amount'],
  ['paymentId', 'Payment ID'],
  ['paymentDateAndTime', 'Payment Date & Time'],
  ['planAssignedAt', 'Plan Assigned At'],
  ['signUpDate', 'Sign Up Date'],
  ['programStartDate', 'Program Start'],
  ['programEndDate', 'Program End'],
  ['leadConversionDate', 'Lead Conversion Date'],
  ['planIncludesCgm', 'Plan Includes CGM'],
  ['cgm', 'CGM'],
  ['cgmBrand', 'CGM Brand'],
  ['sensorCount', 'Sensor Count'],
  ['transmitterCount', 'Transmitter Count'],
  ['bcaDevice', 'BCA Device'],
  ['nutraceuticalsSold', 'Nutraceuticals Sold'],
  ['salesTeam', 'Sales Team'],
  ['deviceAwbNumber', 'Device AWB Number'],
];

function PlanPurchasedSection({ plan }: { plan: LeadDetailFullResponse['plan'] }) {
  const hasAny = PLAN_FIELD_LABELS.some(([key]) => plan[key] !== null && plan[key] !== '');
  if (!hasAny) return null;
  return (
    <SectionBlock title="Plan Purchased" icon={BadgeCheck} tone="success" surface="tinted">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {PLAN_FIELD_LABELS.map(([key, label]) => {
          const raw = plan[key];
          const value = raw === null || raw === '' ? '—' : String(raw);
          const mono = key === 'paymentId' || key === 'deviceAwbNumber';
          return <Field key={key} label={label} value={value} mono={mono} />;
        })}
      </div>
    </SectionBlock>
  );
}

// Map drilldown section id to a tone + icon so every section gets a tasteful
// visual anchor without hardcoding UI concerns into the app-config data.
const SECTION_ICONS: Record<string, { icon: typeof BadgeCheck; tone: 'brand' | 'info' | 'neutral' }> = {
  'contact-source': { icon: User, tone: 'brand' },
  'health-profile': { icon: HeartPulse, tone: 'info' },
};

function DrilldownSection({
  lead,
  section,
}: {
  lead: LeadDetailFullResponse;
  section: AppDrilldownSectionConfig;
}) {
  const meta = SECTION_ICONS[section.id] ?? { icon: ListChecks, tone: 'neutral' as const };
  return (
    <SectionBlock title={section.title} icon={meta.icon} tone={meta.tone}>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {section.fields.map((field) => (
          <Field
            key={field.key}
            label={field.label}
            value={formatLeadFieldValue(lead, field)}
            mono={field.presentation === 'mono'}
          />
        ))}
      </div>
    </SectionBlock>
  );
}

/* ── Summary rail — left column of the workspace ────────────────── */

/**
 * Tonal rules for the summary rail metrics. Kept adjacent to the rail
 * component so the mapping stays explicit and easy to reason about:
 *
 *   Connect rate  → success when > 60%, warning when < 30%, neutral between
 *   Counseling    → success when > 0
 *   FRT           → follows `formatFrt` colour class (RAG green/amber/red)
 */
function connectRateTone(rate: number | null): 'success' | 'warning' | 'neutral' {
  if (rate === null) return 'neutral';
  if (rate >= 60) return 'success';
  if (rate < 30) return 'warning';
  return 'neutral';
}

function SummaryRail({
  lead,
  frt,
  tileFive,
}: {
  lead: LeadDetailFullResponse;
  frt: { text: string; color?: string };
  tileFive: { label: string; value: string };
}) {
  const sourceLine = [lead.source, lead.sourceCampaign].filter(Boolean).join(' · ') || '—';
  const connectTone = connectRateTone(lead.connectRate);
  return (
    <div className="flex flex-col gap-6">
      <SectionBlock title="Contact" icon={User} tone="brand">
        <div className="flex flex-col gap-3">
          <Field label="Phone" value={lead.phone || '—'} mono />
          <Field label="Owner" value={lead.agentName ?? '—'} />
          <Field label="Source" value={sourceLine} />
          <Field label="Prospect ID" value={lead.prospectId} mono />
          <Field label="Lead Created" value={fmtDateTime(lead.createdOn)} />
        </div>
      </SectionBlock>

      <SectionBlock title="Metrics" icon={Activity} tone="info">
        <div className="grid grid-cols-2 gap-x-4 gap-y-4">
          <MetricChip label="FRT" value={frt.text} sub="SLA: 1h" valueClass={frt.color} />
          <MetricChip label="Total Dials" value={lead.totalDials || '—'} />
          <MetricChip
            label="Connect Rate"
            value={lead.connectRate !== null ? `${Math.round(lead.connectRate)}%` : '—'}
            tone={connectTone}
          />
          <MetricChip
            label="Counseling"
            value={lead.historyTruncated ? '?' : lead.counselingCount}
            sub={lead.historyTruncated ? 'history incomplete' : 'calls ≥ 10 min'}
            tone={lead.counselingCount > 0 ? 'success' : 'neutral'}
          />
          <MetricChip label={tileFive.label} value={tileFive.value} />
        </div>
      </SectionBlock>
    </div>
  );
}

/* ── Evaluations tab — audio above scorecard, pagination unchanged ─ */

function EvaluationsPanel({
  evalHistory,
  evalIdx,
  setEvalIdx,
  callHistory,
}: {
  evalHistory: LeadEvalHistoryEntry[];
  evalIdx: number;
  setEvalIdx: (updater: (prev: number) => number) => void;
  callHistory: LeadCallRecord[];
}) {
  const currentEval = evalHistory[evalIdx] ?? null;
  const currentCall = useMemo(
    () => (currentEval ? callHistory.find((c) => c.activityId === currentEval.threadId) : null),
    [currentEval, callHistory],
  );

  if (!currentEval) {
    return (
      <EmptyState
        icon={FileText}
        title="Not yet evaluated"
        description="Select a call from the timeline and click Evaluate."
        fill
      />
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5">
      {evalHistory.length > 1 && (
        <div className="flex items-center gap-3 text-xs text-[var(--text-muted)]">
          <button
            onClick={() => setEvalIdx((index) => Math.min(index + 1, evalHistory.length - 1))}
            disabled={evalIdx >= evalHistory.length - 1}
            className="rounded p-1 hover:bg-[var(--interactive-secondary)] disabled:opacity-40"
            aria-label="Older evaluation"
          >
            ‹
          </button>
          <span>
            Evaluation {evalHistory.length - evalIdx} of {evalHistory.length}
          </span>
          <button
            onClick={() => setEvalIdx((index) => Math.max(index - 1, 0))}
            disabled={evalIdx <= 0}
            className="rounded p-1 hover:bg-[var(--interactive-secondary)] disabled:opacity-40"
            aria-label="Newer evaluation"
          >
            ›
          </button>
        </div>
      )}

      {currentCall?.recordingUrl && (
        <SectionBlock title="Call Recording" icon={Mic} tone="brand">
          <AudioPlayer audioUrl={currentCall.recordingUrl} appId="inside-sales" />
        </SectionBlock>
      )}

      <CallResultPanel thread={currentEval as unknown as ThreadEvalRow} appId="inside-sales" />
    </div>
  );
}

/* ── Page component ────────────────────────────────────────────── */

export function InsideSalesLeadDetail() {
  const appConfig = useAppConfig('inside-sales');
  const drilldownSections = appConfig.collections.drilldowns.lead?.sections ?? [];
  const { prospectId } = useParams<{ prospectId: string }>();
  const navigate = useNavigate();
  // Navigation list: the ordered leads loaded on the listing page. Opening
  // a lead detail directly (no prior listing visit) results in an empty
  // list — prev/next then simply render disabled.
  const leadsList = useLeadsStore((s) => s.leads);

  const listNav = useMemo(() => {
    if (!prospectId) return null;
    const idx = leadsList.findIndex((l) => l.prospectId === prospectId);
    if (idx < 0) return null;
    return {
      index: idx,
      total: leadsList.length,
      prev: idx > 0 ? leadsList[idx - 1].prospectId : null,
      next: idx < leadsList.length - 1 ? leadsList[idx + 1].prospectId : null,
    };
  }, [leadsList, prospectId]);

  const goPrev = listNav?.prev
    ? () => navigate(routes.insideSales.leadDetail(listNav.prev as string))
    : undefined;
  const goNext = listNav?.next
    ? () => navigate(routes.insideSales.leadDetail(listNav.next as string))
    : undefined;

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
  const tileFive = lead.preferredCallTime
    ? { label: 'Callback Adherence', value: fmtAdherence(lead.callbackAdherenceSeconds) }
    : { label: 'Lead Age', value: `${lead.leadAgeDays}d` };

  const evaluatableCall = [...lead.callHistory].find((call) => call.recordingUrl && call.evalScore === null);
  const canEvaluate = Boolean(evaluatableCall);

  const activeEvalActivityId = lead.evalHistory[evalIdx]?.threadId ?? null;

  const overviewTab = (
    <div className="flex min-h-0 flex-1 flex-col gap-8">
      <PlanPurchasedSection plan={lead.plan} />
      {drilldownSections.map((section) => (
        <DrilldownSection key={section.id} lead={lead} section={section} />
      ))}
    </div>
  );

  const timelineTab = (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      {lead.historyTruncated && (
        <div className="rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-400">
          Showing the first 200 calls — call history may be incomplete. Metrics marked with a warning may be inaccurate.
        </div>
      )}
      <LeadCallTimeline callHistory={lead.callHistory} activeEvalActivityId={activeEvalActivityId} />
    </div>
  );

  const evaluationsTab = (
    <EvaluationsPanel
      evalHistory={lead.evalHistory}
      evalIdx={evalIdx}
      setEvalIdx={setEvalIdx}
      callHistory={lead.callHistory}
    />
  );

  const tabs: RecordWorkspaceTab[] = [
    { id: 'overview', label: 'Overview', content: overviewTab },
    {
      id: 'timeline',
      label: 'Call Timeline',
      badge: lead.callHistory.length > 0 ? String(lead.callHistory.length) : undefined,
      content: timelineTab,
    },
    {
      id: 'evaluations',
      label: 'Evaluations',
      badge: lead.evalHistory.length > 0 ? String(lead.evalHistory.length) : undefined,
      content: evaluationsTab,
    },
  ];

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
    <>
      {listNav && (
        <RecordNavigator
          recordLabel="lead"
          current={listNav.index + 1}
          total={listNav.total}
          onPrev={goPrev}
          onNext={goNext}
          disableShortcuts={evalOpen}
        />
      )}
      <span title={canEvaluate ? undefined : 'No unevaluated recordings'}>
        <Button size="sm" disabled={!canEvaluate} onClick={() => setEvalOpen(true)}>
          Evaluate
        </Button>
      </span>
    </>
  );

  return (
    <PageSurface
      icon={PAGE_METADATA.leadDetail.icon}
      title={displayName}
      subtitle={subtitle}
      back={{ to: routes.insideSales.listing, label: 'Leads' }}
      actions={actions}
    >
      <RecordWorkspace
        summary={<SummaryRail lead={lead} frt={frt} tileFive={tileFive} />}
        tabs={tabs}
        defaultTab="overview"
      />

      {evalOpen && evaluatableCall && (
        <NewInsideSalesEvalOverlay
          onClose={() => { setEvalOpen(false); load(); }}
          preSelectedCallIds={[evaluatableCall.activityId]}
        />
      )}
    </PageSurface>
  );
}
