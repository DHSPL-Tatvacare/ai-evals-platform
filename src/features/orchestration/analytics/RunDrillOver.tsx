import { useMemo } from 'react';
import { ExternalLink, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  Badge,
  Card,
  ConnectionProviderLogo,
  DataTable,
  FunnelCard,
  IconButton,
  LoadingState,
  type ColumnDef,
} from '@/components/ui';
import { ChartRenderer } from '@/features/analytics/components/ChartRenderer';
import { routes } from '@/config/routes';
import { useOrchestrationRunDetail } from './queries';
import { formatUsd } from './format';
import type { AnalyticsScope, OrchestrationRunAction } from './types';

interface RunDrillOverProps {
  runId: string;
  appId: string;
  scope: AnalyticsScope;
  onClose: () => void;
  labelledBy?: string;
}

const BUCKET_LABELS: { key: keyof OutcomeBuckets; label: string }[] = [
  { key: 'positive', label: 'Positive' },
  { key: 'reached', label: 'Reached' },
  { key: 'noResponse', label: 'No response' },
  { key: 'failed', label: 'Failed' },
  { key: 'inFlight', label: 'In-flight' },
];

interface OutcomeBuckets {
  positive: number;
  reached: number;
  noResponse: number;
  failed: number;
  inFlight: number;
}

export function RunDrillOver({ runId, appId, scope, onClose, labelledBy }: RunDrillOverProps) {
  const { data, isLoading } = useOrchestrationRunDetail(runId, { appId, scope });

  const donutData = useMemo(() => {
    if (!data) return [];
    return BUCKET_LABELS.map(({ key, label }) => ({ name: label, value: data.buckets[key] })).filter(
      (d) => d.value > 0,
    );
  }, [data]);

  const funnelStages = useMemo(() => {
    if (!data) return [];
    return BUCKET_LABELS.map(({ key, label }) => ({ key, label, value: data.buckets[key] }));
  }, [data]);

  const actionColumns: ColumnDef<OrchestrationRunAction>[] = [
    { key: 'recipient', header: 'Recipient', textBehavior: 'truncate', render: (a) => a.contact ?? a.recipientId },
    { key: 'channel', header: 'Channel', width: 'w-24', render: (a) => a.channel },
    { key: 'action', header: 'Action', width: 'w-32', textBehavior: 'truncate', render: (a) => a.actionType },
    {
      key: 'outcome',
      header: 'Outcome',
      width: 'w-28',
      render: (a) => (a.outcomeBucket ? <Badge variant="neutral">{a.outcomeBucket}</Badge> : '—'),
    },
    {
      key: 'cost',
      header: 'Cost',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums',
      headerClassName: 'text-right',
      render: (a) => (a.cost != null ? formatUsd(a.cost) : '—'),
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--border-subtle)] p-4">
        <div className="min-w-0">
          <h2 id={labelledBy} className="truncate text-base font-semibold text-[var(--text-primary)]">
            {data?.workflowName ?? 'Run detail'}
          </h2>
          {data && (
            <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">
              {data.status} · {data.triggeredBy} · {data.cohortSize} recipients · {formatUsd(data.spend)}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link
            to={routes.insideSales.campaignRunDetail(runId)}
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-[12px] font-medium text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open full run
          </Link>
          <IconButton icon={X} label="Close" onClick={onClose} />
        </div>
      </div>

      {isLoading || !data ? (
        <div className="flex-1">
          <LoadingState />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="flex flex-col p-4">
              <h3 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">Outcomes</h3>
              {donutData.length === 0 ? (
                <p className="py-6 text-center text-xs text-[var(--text-muted)]">No outcomes recorded</p>
              ) : (
                <ChartRenderer
                  type="donut"
                  data={donutData}
                  xKey="name"
                  yKey="value"
                  height={240}
                  legendPosition="right"
                  hideSliceLabels
                />
              )}
            </Card>
            <FunnelCard title="This run" stages={funnelStages} />
          </div>

          <Card className="p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Node path</h3>
            {data.nodeSteps.length === 0 ? (
              <p className="text-xs text-[var(--text-muted)]">No node steps recorded.</p>
            ) : (
              <ol className="flex flex-wrap items-center gap-2">
                {data.nodeSteps.map((step) => (
                  <li
                    key={step.nodeStepId}
                    className="flex items-center gap-1.5 rounded-[var(--radius-default)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 py-1 text-[12px]"
                  >
                    <ConnectionProviderLogo provider={step.nodeType} size={16} />
                    <span className="text-[var(--text-secondary)]">{step.nodeId}</span>
                    <Badge variant="neutral">{step.status}</Badge>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <Card className="flex min-h-0 flex-col p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">Action log</h3>
              <span className="text-[11.5px] text-[var(--text-muted)]">{data.actionsTotal} actions</span>
            </div>
            <DataTable
              columns={actionColumns}
              data={data.actions}
              keyExtractor={(a) => a.actionId}
              minWidth="0"
              emptyTitle="No actions"
              emptyDescription="This run has no recorded actions yet."
            />
          </Card>
        </div>
      )}
    </div>
  );
}
