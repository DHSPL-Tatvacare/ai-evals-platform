import { useNavigate } from 'react-router-dom';
import type { AppId } from '@/types';
import type { RuleComplianceHeatmap } from '@/types/crossRunAnalytics';
import { runDetailForApp } from '@/config/routes';
import SectionHeader from '../report/shared/SectionHeader';
import { Heatmap, type HeatmapCell } from '@/components/report/Heatmap';

interface Props {
  appId: AppId;
  heatmap: RuleComplianceHeatmap;
}

export default function ComplianceHeatmapTab({ appId, heatmap }: Props) {
  const navigate = useNavigate();

  const columns = heatmap.runs.map((r) => ({
    id: r.runId,
    label: r.runName || r.runId.slice(0, 8),
    sublabel: r.createdAt
      ? new Date(r.createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : null,
  }));

  const rows = heatmap.rows.map((r) => ({
    id: r.ruleId,
    label: r.ruleId,
    sublabel: r.section,
    cells: r.cells.map((value): HeatmapCell => ({ value })),
    trailing: { value: r.avgRate },
  }));

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Rule Compliance Across Runs"
        description="Each cell shows the pass rate for a rule in a specific run. Rules sorted by worst average compliance."
      />

      <Heatmap
        columns={columns}
        rows={rows}
        rowHeaderLabel="Rule"
        onColumnClick={(id: string) => navigate(runDetailForApp(appId, id))}
        emptyDescription="No rule compliance data found in reports. Run evaluations with correctness evaluation enabled."
      />
    </div>
  );
}
