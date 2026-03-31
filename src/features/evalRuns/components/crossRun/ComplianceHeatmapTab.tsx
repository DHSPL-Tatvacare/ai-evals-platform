import { useNavigate } from 'react-router-dom';
import type { AppId } from '@/types';
import type { RuleComplianceHeatmap } from '@/types/crossRunAnalytics';
import { routes } from '@/config/routes';
import SectionHeader from '../report/shared/SectionHeader';
import Heatmap from './Heatmap';

interface Props {
  appId: AppId;
  heatmap: RuleComplianceHeatmap;
}

export default function ComplianceHeatmapTab({ appId, heatmap }: Props) {
  const navigate = useNavigate();

  const columnHeaders = heatmap.runs.map((r) => {
    const date = r.createdAt
      ? new Date(r.createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : '';
    return {
      id: r.runId,
      label: r.runName || r.runId.slice(0, 8),
      sublabel: date,
    };
  });

  const rows = heatmap.rows.map((r) => ({
    id: r.ruleId,
    label: r.ruleId,
    sublabel: r.section,
    cells: r.cells,
    average: r.avgRate,
  }));

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Rule Compliance Across Runs"
        description="Each cell shows the pass rate for a rule in a specific run. Rules sorted by worst average compliance."
      />

      <Heatmap
        columnHeaders={columnHeaders}
        rows={rows}
        rowHeaderLabel="Rule"
        onColumnClick={(id) => navigate(appId === 'inside-sales' ? routes.insideSales.runDetail(id) : routes.kaira.runDetail(id))}
        emptyMessage="No rule compliance data found in reports. Run evaluations with correctness evaluation enabled."
      />
    </div>
  );
}
