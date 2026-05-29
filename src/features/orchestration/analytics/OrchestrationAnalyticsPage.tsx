import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { format, parseISO, startOfMonth, subDays } from 'date-fns';
import {
  Activity,
  BarChart3,
  CircleCheck,
  CircleX,
  Coins,
  Megaphone,
  RefreshCw,
  Sparkles,
  Users,
  Wifi,
} from 'lucide-react';
import {
  Button,
  Card,
  Combobox,
  ConnectionProviderLogo,
  DataTable,
  DateRangePicker,
  FunnelCard,
  MetricBreakdownCard,
  PageSurface,
  RightSlideOverShell,
  ScopeToggle,
  StatCard,
  Tabs,
  TrendCard,
  type ColumnDef,
  type DateRangePreset,
  type MetricBreakdownColumn,
} from '@/components/ui';
import { useCurrentAppId } from '@/hooks';
import { cn } from '@/utils/cn';
import {
  useOrchestrationBreakdown,
  useOrchestrationOverview,
  useOrchestrationRuns,
  useOrchestrationSignals,
} from './queries';
import { useCanSeeTenantAnalytics } from './useCanSeeTenantAnalytics';
import { RunDrillOver } from './RunDrillOver';
import { formatInt, formatPct, formatUsd } from './format';
import type {
  AnalyticsScope,
  BreakdownDimension,
  OrchestrationBreakdownRow,
  OrchestrationRunRow,
} from './types';

const PRESETS: DateRangePreset[] = [
  { id: '7d', label: 'Last 7 days' },
  { id: '30d', label: 'Last 30 days' },
  { id: '90d', label: 'Last 90 days' },
  { id: 'mtd', label: 'Month to date' },
];
const PRESET_IDS = new Set(PRESETS.map((p) => p.id));
const CUSTOM_RE = /^\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$/;
const DEFAULT_RANGE = '30d';

function resolveRange(range: string): { from: string; to: string } {
  const now = new Date();
  if (CUSTOM_RE.test(range)) {
    const [from, to] = range.split(':');
    return { from, to };
  }
  const start =
    range === '7d'
      ? subDays(now, 7)
      : range === '90d'
        ? subDays(now, 90)
        : range === 'mtd'
          ? startOfMonth(now)
          : subDays(now, 30);
  return { from: format(start, 'yyyy-MM-dd'), to: format(now, 'yyyy-MM-dd') };
}

const BREAKDOWN_TABS: { id: BreakdownDimension; label: string; nameHeader: string }[] = [
  { id: 'campaign', label: 'By campaign', nameHeader: 'Campaign' },
  { id: 'channel', label: 'By channel', nameHeader: 'Channel' },
  { id: 'connection', label: 'By connection', nameHeader: 'Connection' },
];

export function OrchestrationAnalyticsPage() {
  const appId = useCurrentAppId();
  const canSeeTenant = useCanSeeTenantAnalytics();
  const [searchParams, setSearchParams] = useSearchParams();

  const requestedScope = (searchParams.get('scope') as AnalyticsScope | null) ?? (canSeeTenant ? 'tenant' : 'mine');
  const scope: AnalyticsScope = requestedScope === 'tenant' && canSeeTenant ? 'tenant' : 'mine';
  const range = searchParams.get('range') ?? DEFAULT_RANGE;
  const { from, to } = useMemo(() => resolveRange(range), [range]);

  const params = useMemo(() => ({ appId, scope, from, to }), [appId, scope, from, to]);

  const [campaignFilter, setCampaignFilter] = useState<string>('');
  const [openRunId, setOpenRunId] = useState<string | null>(null);

  const overview = useOrchestrationOverview(params);
  const signals = useOrchestrationSignals(params);
  const campaignBreakdown = useOrchestrationBreakdown({ ...params, dimension: 'campaign' });
  const runs = useOrchestrationRuns(params);

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set(key, value);
    setSearchParams(next, { replace: true });
  };

  const ov = overview.data;

  const campaignRows = useMemo(() => campaignBreakdown.data?.rows ?? [], [campaignBreakdown.data?.rows]);
  const campaignOptions = useMemo(
    () => [
      { value: '', label: 'All campaigns' },
      ...campaignRows.map((r) => ({ value: r.key, label: r.label })),
    ],
    [campaignRows],
  );

  // Trend derived from the runs rows (real data) grouped by start day, since the
  // overview endpoint returns no time series. Stacked area by outcome bucket.
  const trendData = useMemo(() => buildTrend(runs.data?.rows ?? []), [runs.data?.rows]);

  // The funnel adapts to the selected campaign when one is picked, else the all-up reach.
  const funnelStages = useMemo(() => {
    const row = campaignFilter ? campaignRows.find((r) => r.key === campaignFilter) : null;
    const recipients = row?.recipients ?? ov?.recipients ?? 0;
    const reached = row ? row.reached + row.positive : (ov?.reached ?? 0) + (ov?.positive ?? 0);
    const positive = row?.positive ?? ov?.positive ?? 0;
    return [
      { key: 'recipients', label: 'Recipients', value: recipients },
      { key: 'reached', label: 'Reached', value: reached },
      { key: 'positive', label: 'Positive', value: positive },
    ];
  }, [campaignFilter, campaignRows, ov]);

  const runColumns: ColumnDef<OrchestrationRunRow>[] = [
    { key: 'workflow', header: 'Workflow', textBehavior: 'truncate', render: (r) => r.workflowName },
    { key: 'channel', header: 'Channel', width: 'w-24', render: (r) => r.channel ?? '—' },
    { key: 'trigger', header: 'Trigger', width: 'w-24', render: (r) => r.triggeredBy },
    { key: 'status', header: 'Status', width: 'w-28', render: (r) => r.status },
    {
      key: 'cohort',
      header: 'Cohort',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums',
      headerClassName: 'text-right',
      render: (r) => formatInt(r.cohortSize),
    },
    {
      key: 'reached',
      header: 'Reached',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums',
      headerClassName: 'text-right',
      render: (r) => formatInt(r.reached),
    },
    {
      key: 'positive',
      header: 'Positive',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums',
      headerClassName: 'text-right',
      render: (r) => formatInt(r.positive),
    },
    {
      key: 'cost',
      header: 'Cost',
      width: 'w-24',
      cellClassName: 'text-right tabular-nums font-semibold',
      headerClassName: 'text-right',
      render: (r) => formatUsd(r.cost),
    },
  ];

  const refresh = () => {
    void overview.refetch?.();
    void signals.refetch?.();
    void campaignBreakdown.refetch?.();
    void runs.refetch?.();
  };

  return (
    <PageSurface
      icon={BarChart3}
      title="Campaign analytics"
      subtitle="Outcomes, channels, connections, and spend across your campaigns."
      filters={
        <div className="flex flex-wrap items-center gap-3">
          <ScopeToggle
            value={scope}
            canSeeTenant={canSeeTenant}
            onChange={(next) => setParam('scope', next)}
          />
          <DateRangePicker
            presets={PRESETS}
            activePreset={PRESET_IDS.has(range) ? range : null}
            from={CUSTOM_RE.test(range) ? range.split(':')[0] : null}
            to={CUSTOM_RE.test(range) ? range.split(':')[1] : null}
            onPresetSelect={(id) => setParam('range', id)}
            onCustomRange={(f, t) => setParam('range', `${f}:${t}`)}
          />
        </div>
      }
      actions={
        <Button
          variant="secondary"
          size="sm"
          icon={RefreshCw}
          iconOnly
          aria-label="Refresh analytics"
          title="Refresh analytics"
          onClick={refresh}
        >
          Refresh
        </Button>
      }
    >
      <div className="flex h-full min-h-0 flex-col space-y-4 pb-6">
        <SignalsBox
          signals={signals.data?.signals ?? []}
          generatedAt={signals.data?.generatedAt ?? null}
        />

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <StatCard icon={Megaphone} label="Campaigns" value={formatInt(ov?.campaigns ?? 0)} />
          <StatCard icon={Users} label="Recipients" value={formatInt(ov?.recipients ?? 0)} />
          <StatCard
            icon={Wifi}
            label="Connected %"
            value={formatPct((ov?.reached ?? 0) + (ov?.positive ?? 0), ov?.recipients ?? 0)}
          />
          <StatCard
            icon={CircleCheck}
            label="Positive %"
            value={formatPct(ov?.positive ?? 0, ov?.recipients ?? 0)}
            tone="positive"
          />
          <StatCard
            icon={CircleX}
            label="Failed %"
            value={formatPct(ov?.failed ?? 0, ov?.recipients ?? 0)}
            tone={ov && ov.failed > 0 ? 'danger' : 'neutral'}
          />
          <StatCard icon={Coins} label="Spend" value={formatUsd(ov?.spend ?? 0)} />
          <StatCard
            icon={Activity}
            label="In-flight"
            value={formatInt(ov?.inFlightRuns ?? 0)}
            hint={ov ? `${formatInt(ov.inFlight)} recipients` : undefined}
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <TrendCard
            title="Outcomes over time"
            data={trendData}
            xKey="day"
            seriesKeys={['positive', 'reached', 'failed']}
          />
          <FunnelCard
            title="Conversion funnel"
            stages={funnelStages}
            headerControl={
              <div className="w-48">
                <Combobox
                  options={campaignOptions}
                  value={campaignFilter}
                  onChange={(v) => setCampaignFilter(v)}
                  placeholder="All campaigns"
                  size="sm"
                />
              </div>
            }
          />
        </div>

        <BreakdownTabs params={params} />

        <Card className="flex min-h-0 flex-col p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">Recent runs</h3>
            <span className="text-[11.5px] text-[var(--text-muted)]">{runs.data?.total ?? 0} runs</span>
          </div>
          <DataTable
            columns={runColumns}
            data={runs.data?.rows ?? []}
            keyExtractor={(r) => r.runId}
            minWidth="0"
            onRowClick={(r) => setOpenRunId(r.runId)}
            emptyIcon={BarChart3}
            emptyTitle="No runs"
            emptyDescription="No campaign runs in the selected range."
          />
        </Card>
      </div>

      <RightSlideOverShell
        isOpen={openRunId !== null}
        onClose={() => setOpenRunId(null)}
        widthClassName="w-[var(--overlay-width-lg)] max-w-[92vw]"
        labelledBy="run-drillover-title"
      >
        {openRunId && (
          <RunDrillOver
            runId={openRunId}
            appId={appId}
            scope={scope}
            onClose={() => setOpenRunId(null)}
            labelledBy="run-drillover-title"
          />
        )}
      </RightSlideOverShell>
    </PageSurface>
  );
}

interface TrendPoint {
  day: string;
  positive: number;
  reached: number;
  failed: number;
}

function buildTrend(rows: OrchestrationRunRow[]): Record<string, unknown>[] {
  const byDay = new Map<string, TrendPoint>();
  for (const r of rows) {
    if (!r.startedAt) continue;
    const day = format(parseISO(r.startedAt), 'yyyy-MM-dd');
    const point = byDay.get(day) ?? { day, positive: 0, reached: 0, failed: 0 };
    point.positive += r.positive;
    point.reached += r.reached;
    byDay.set(day, point);
  }
  return [...byDay.values()].sort((a, b) => a.day.localeCompare(b.day)) as unknown as Record<string, unknown>[];
}

function BreakdownTabs({ params }: { params: { appId: string; scope: AnalyticsScope; from: string; to: string } }) {
  const tabs = BREAKDOWN_TABS.map((tab) => ({
    id: tab.id,
    label: tab.label,
    content: <BreakdownPanel dimension={tab.id} nameHeader={tab.nameHeader} params={params} />,
  }));
  return (
    <Card className="flex min-h-0 flex-col p-2">
      <Tabs tabs={tabs} defaultTab="campaign" mountStrategy="active-only" />
    </Card>
  );
}

const BREAKDOWN_COLUMNS: MetricBreakdownColumn<OrchestrationBreakdownRow>[] = [
  { key: 'recipients', header: 'Recipients', render: (r) => formatInt(r.recipients) },
  { key: 'dispatched', header: 'Dispatched', render: (r) => formatInt(r.dispatched) },
  { key: 'positive', header: 'Positive', render: (r) => formatInt(r.positive) },
  { key: 'negative', header: 'Negative', render: (r) => formatInt(r.noResponse + r.failed) },
  { key: 'avgCost', header: 'Avg cost', render: (r) => formatUsd(r.avgCost) },
  { key: 'cost', header: 'Cost', render: (r) => formatUsd(r.cost) },
];

function BreakdownPanel({
  dimension,
  nameHeader,
  params,
}: {
  dimension: BreakdownDimension;
  nameHeader: string;
  params: { appId: string; scope: AnalyticsScope; from: string; to: string };
}) {
  const { data } = useOrchestrationBreakdown({ ...params, dimension });
  const rows = data?.rows ?? [];
  return (
    <MetricBreakdownCard
      nameHeader={nameHeader}
      rows={rows}
      columns={BREAKDOWN_COLUMNS}
      keyExtractor={(r) => r.key}
      renderName={(r) => (
        <span className="flex items-center gap-2">
          {r.provider && <ConnectionProviderLogo provider={r.provider} size={16} />}
          <span className="truncate">{r.label}</span>
        </span>
      )}
      searchPlaceholder={`Search ${nameHeader.toLowerCase()}`}
      searchMatch={(r, q) => r.label.toLowerCase().includes(q)}
      emptyTitle="No data"
      emptyDescription="No rows in the selected range."
    />
  );
}

interface SignalsBoxProps {
  signals: { severity: string; title: string; detail: string }[];
  generatedAt: string | null;
}

function SignalsBox({ signals, generatedAt }: SignalsBoxProps) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--chip-brand-border)] bg-[var(--surface-brand-subtle)] p-5 shadow-[var(--shadow-md)]">
      <div className="mb-3.5 flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--interactive-primary)] shadow-[var(--shadow-sm)]">
          <Sparkles className="h-[18px] w-[18px] text-white" />
        </span>
        <div className="flex flex-col">
          <h3 className="text-[15px] font-semibold leading-tight text-[var(--text-primary)]">Signals to watch</h3>
          <span className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">AI summary</span>
        </div>
      </div>
      {signals.length === 0 ? (
        <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
          Nothing unusual to flag for the selected range.
        </p>
      ) : (
        <ul className="space-y-2">
          {signals.map((sig, i) => (
            <li key={i} className="flex items-start gap-2.5 text-[13px] leading-relaxed text-[var(--text-secondary)]">
              <span
                className={cn(
                  'mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full',
                  sig.severity === 'warning' && 'bg-[var(--color-warning)]',
                  (sig.severity === 'error' || sig.severity === 'critical') && 'bg-[var(--color-error)]',
                  sig.severity !== 'warning' &&
                    sig.severity !== 'error' &&
                    sig.severity !== 'critical' &&
                    'bg-[var(--color-info)]',
                )}
              />
              <span>
                <span className="font-medium text-[var(--text-primary)]">{sig.title}</span>
                {' — '}
                {sig.detail}
              </span>
            </li>
          ))}
        </ul>
      )}
      {generatedAt && (
        <p className="mt-2 text-[11px] text-[var(--text-muted)]">Generated {format(parseISO(generatedAt), 'd MMM, HH:mm')}</p>
      )}
    </div>
  );
}
