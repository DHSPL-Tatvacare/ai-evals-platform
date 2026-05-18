import { useNavigate } from 'react-router-dom';
import type { AppId } from '@/types';
import type { AdversarialHeatmap } from '@/types/crossRunAnalytics';
import { runDetailForApp } from '@/config/routes';
import SectionHeader from '../report/shared/SectionHeader';
import { Heatmap, type HeatmapCell } from '@/components/report/Heatmap';

interface Props {
  appId: AppId;
  heatmap: AdversarialHeatmap;
}

export default function AdversarialHeatmapTab({ appId, heatmap }: Props) {
  const navigate = useNavigate();

  const columns = heatmap.runs.map((r) => ({
    id: r.runId,
    label: r.runName || r.runId.slice(0, 8),
    sublabel: r.createdAt
      ? new Date(r.createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : null,
  }));

  const rows = heatmap.rows.map((r) => ({
    id: r.goal,
    label: r.goal,
    cells: r.cells.map((value): HeatmapCell => ({ value })),
    trailing: { value: r.avgPassRate },
  }));

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Adversarial Goal Resilience"
        description="Pass rate per attack goal across adversarial runs."
      />

      <Heatmap
        columns={columns}
        rows={rows}
        rowHeaderLabel="Goal"
        onColumnClick={(id: string) => navigate(runDetailForApp(appId, id))}
        emptyDescription="No adversarial runs with reports found."
      />
    </div>
  );
}
