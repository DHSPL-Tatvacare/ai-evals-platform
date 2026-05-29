import { useCallback, useState } from 'react';
import { Download, ExternalLink, X } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button, IconButton, LoadingState } from '@/components/ui';
import { exportRunPdf } from '@/services/api/orchestrationAnalytics';
import { notificationService } from '@/services/notifications';
import { useOrchestrationRoutes } from '../hooks/useOrchestrationRoutes';
import { useOrchestrationRunReport } from './queries';
import { CampaignRunReportView } from './report/CampaignRunReportView';
import type { AnalyticsScope } from './types';

interface RunDrillOverProps {
  runId: string;
  appId: string;
  scope: AnalyticsScope;
  onClose: () => void;
  labelledBy?: string;
}

export function RunDrillOver({ runId, appId, scope, onClose, labelledBy }: RunDrillOverProps) {
  const orchestrationRoutes = useOrchestrationRoutes();
  const { data, isLoading } = useOrchestrationRunReport(runId, { appId, scope });
  const [exporting, setExporting] = useState(false);

  const handleExportPdf = useCallback(async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const blob = await exportRunPdf(runId, { appId, scope });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `campaign-run-${runId.slice(0, 8)}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      notificationService.success('PDF exported');
    } catch (err) {
      const detail = err instanceof Error ? err.message : 'Please try again.';
      notificationService.error(detail, 'PDF export failed');
    } finally {
      setExporting(false);
    }
  }, [appId, exporting, runId, scope]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--border-subtle)] p-4">
        <h2
          id={labelledBy}
          className="min-w-0 truncate text-base font-semibold text-[var(--text-primary)]"
        >
          {data?.workflowName ?? 'Run detail'}
        </h2>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            icon={Download}
            isLoading={exporting}
            disabled={exporting || !data}
            onClick={() => void handleExportPdf()}
          >
            Export PDF
          </Button>
          <Link
            to={orchestrationRoutes.campaignRunDetail(runId)}
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--interactive-secondary)] px-2.5 py-1.5 text-[12px] font-medium text-[var(--text-primary)] hover:bg-[var(--interactive-secondary-hover)]"
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
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
          <CampaignRunReportView report={data} />
        </div>
      )}
    </div>
  );
}
