import { useState } from 'react';
import { DataTable, type ColumnDef } from '@/components/ui';
import { cn } from '@/utils/cn';
import type {
  RunReportChannel,
  RunReportRecipient,
  RunReportRecipientChannel,
} from '../types';
import { capabilityLabel } from './labels';
import { formatDuration } from '../format';

interface RecipientTableProps {
  recipients: RunReportRecipient[];
  channels: RunReportChannel[];
  totalCount: number;
  printMode?: boolean;
}

const STAGE_DOT_LIMIT = 3;
const RECIPIENTS_PER_PAGE = 10;

function findChannel(
  channels: RunReportRecipientChannel[],
  capability: string,
): RunReportRecipientChannel | undefined {
  return channels.find((channel) => channel.capability === capability);
}

/** Lit dots for the first N stages of a channel, lit up to the stage the
 *  recipient reached. Stage order + labels come from the report channel — never
 *  a hardcoded S/D/R list. */
function StageDots({
  stages,
  stageReached,
}: {
  stages: RunReportChannel['stages'];
  stageReached?: string | null;
}) {
  const shown = stages.slice(0, STAGE_DOT_LIMIT);
  const reachedIndex = stageReached
    ? shown.findIndex((stage) => stage.key === stageReached)
    : -1;
  return (
    <span className="inline-flex items-center gap-1.5">
      {shown.map((stage, index) => {
        const lit = reachedIndex >= 0 && index <= reachedIndex;
        return (
          <span
            key={stage.key}
            title={stage.label}
            className={cn(
              'h-2 w-2 rounded-full',
              lit ? 'bg-[var(--color-success)]' : 'bg-[var(--bg-tertiary)]',
            )}
          />
        );
      })}
    </span>
  );
}

function attributeSummary(attributes: Record<string, unknown>): string {
  return Object.values(attributes)
    .map((value) => String(value ?? '').trim())
    .filter((value) => value && value !== 'null' && value !== 'undefined')
    .join(' · ');
}

export function RecipientTable({
  recipients,
  channels,
  totalCount,
  printMode = false,
}: RecipientTableProps) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(recipients.length / RECIPIENTS_PER_PAGE));
  const pageRows = printMode
    ? recipients
    : recipients.slice((page - 1) * RECIPIENTS_PER_PAGE, page * RECIPIENTS_PER_PAGE);

  const columns: ColumnDef<RunReportRecipient>[] = [
    {
      key: 'contact',
      header: 'Contact',
      textBehavior: 'wrap',
      render: (row) => (
        <div className="min-w-0">
          <p className="font-medium text-[var(--text-primary)]">
            {row.displayName ?? (row.contactLast4 ? `••• ${row.contactLast4}` : '—')}
          </p>
          {row.displayName && row.contactLast4 ? (
            <p className="text-[11px] text-[var(--text-muted)]">••• {row.contactLast4}</p>
          ) : null}
          {Object.keys(row.attributes).length > 0 ? (
            <p className="text-[11px] text-[var(--text-muted)]">{attributeSummary(row.attributes)}</p>
          ) : null}
        </div>
      ),
    },
  ];

  // One outcome column per channel in the run, in channel order. Each column
  // shows the per-recipient outcome, stage-progress dots, and a talk-time line
  // when that channel's per-recipient metrics carry a duration. All keyed off
  // the channel's own capability — no per-vendor branch.
  for (const channel of channels) {
    columns.push({
      key: `channel:${channel.capability}`,
      header: capabilityLabel(channel.capability),
      textBehavior: 'wrap',
      render: (row) => {
        const recipientChannel = findChannel(row.channels, channel.capability);
        if (!recipientChannel) return <span className="text-[var(--text-muted)]">—</span>;
        const duration = recipientChannel.metrics.durationSec;
        return (
          <div className="min-w-0 space-y-1">
            <div className="flex items-center gap-2">
              {channel.stages.length > 0 ? (
                <StageDots
                  stages={channel.stages}
                  stageReached={recipientChannel.stageReached}
                />
              ) : null}
              <span className="text-[var(--text-secondary)]">
                {recipientChannel.outcomeBucket ?? '—'}
              </span>
            </div>
            {typeof duration === 'number' ? (
              <p className="text-[11px] tabular-nums text-[var(--text-muted)]">
                {formatDuration(duration)} talk time
              </p>
            ) : null}
          </div>
        );
      },
    });
  }

  columns.push({
    key: 'snippet',
    header: 'Summary',
    cellVariant: 'prose',
    textBehavior: 'wrap',
    render: (row) => {
      const summary = row.channels.map((c) => c.summary).find((s) => s && s.trim());
      return summary ? (
        <span>{summary}</span>
      ) : (
        <span className="text-[var(--text-muted)]">No summary</span>
      );
    },
  });

  return (
    <div className="space-y-2">
      <p className="text-[11px] text-[var(--text-muted)]">
        Top {recipients.length} of {totalCount} contacts · per-channel outcome and engagement
      </p>
      <DataTable
        columns={columns}
        data={pageRows}
        keyExtractor={(row) => row.recipientId}
        stickyHeader={!printMode}
        emptyTitle="No contacts"
        emptyDescription="This run has no recipient activity yet."
        pagination={
          printMode || recipients.length <= RECIPIENTS_PER_PAGE
            ? undefined
            : {
                page,
                totalPages,
                onPageChange: setPage,
                pageSize: RECIPIENTS_PER_PAGE,
                totalItems: recipients.length,
                showCount: true,
              }
        }
      />
    </div>
  );
}
