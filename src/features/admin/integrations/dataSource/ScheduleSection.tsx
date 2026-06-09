import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import cronstrue from 'cronstrue';
import { CalendarClock, Plus } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { routes } from '@/config/routes';
import { ScheduleOverlay } from '@/features/admin/scheduledJobs/components/ScheduleOverlay';
import { useScheduledJobsStore } from '@/stores/scheduledJobsStore';

function cadence(cron: string): string {
  try {
    return cronstrue.toString(cron, { use24HourTimeFormat: true });
  } catch {
    return cron;
  }
}

/** Recurring-sync schedules for this dataset. Lists matching schedules with their cadence and
 *  links to the Scheduled Jobs page; the create overlay is reused as-is (persisting the link is
 *  backend-side). */
export function ScheduleSection({
  connectionId,
  recordType,
  appId,
}: {
  connectionId: string;
  recordType: string;
  appId: string;
}) {
  const schedules = useScheduledJobsStore((s) => s.schedules);
  const load = useScheduledJobsStore((s) => s.load);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    void load();
  }, [load]);

  // The per-dataset source id == its schedule key (backend resolver). Matching strictly on the key
  // means one dataset never lists — or can overwrite — another dataset's or connection's schedule.
  const sourceId = `${connectionId}:${recordType}`;
  const matching = useMemo(
    () => schedules.filter((s) => s.jobType === 'sync-crm-source' && s.scheduleKey === sourceId),
    [schedules, sourceId],
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-[var(--text-muted)]" />
          <p className="text-[13px] font-medium text-[var(--text-primary)]">Schedule</p>
        </div>
        <Button variant="secondary" size="sm" icon={Plus} onClick={() => setCreating(true)}>
          Add schedule
        </Button>
      </div>

      {matching.length === 0 ? (
        <p className="text-[12px] text-[var(--text-secondary)]">
          No recurring sync yet. Add a schedule to keep this dataset fresh on a cadence.
        </p>
      ) : (
        <ul className="space-y-2">
          {matching.map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between gap-3 rounded-[var(--radius-default)] border border-[var(--border-subtle)] px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-[13px] text-[var(--text-primary)]">{s.name}</p>
                <p className="text-[12px] text-[var(--text-secondary)]">
                  {cadence(s.cron)}
                  {s.enabled ? '' : ' · paused'}
                </p>
              </div>
              <Link
                to={routes.adminScheduledJobs}
                className="shrink-0 text-[12px] text-[var(--text-brand)] hover:underline"
              >
                View in Scheduled Jobs
              </Link>
            </li>
          ))}
        </ul>
      )}

      {creating ? (
        <ScheduleOverlay
          schedule={null}
          launchContext={{ appId, jobType: 'sync-crm-source', sourceId }}
          onClose={() => setCreating(false)}
        />
      ) : null}
    </div>
  );
}
