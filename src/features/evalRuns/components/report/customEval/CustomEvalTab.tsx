import type { CustomEvaluationsReport } from '@/types/reports';
import SectionHeader from '../shared/SectionHeader';
import CustomNarrative from './CustomNarrative';
import EvaluatorCard from './EvaluatorCard';

interface Props {
  report: CustomEvaluationsReport;
}

export default function CustomEvalTab({ report }: Props) {
  return (
    <div className="space-y-8 pt-2">
      <section>
        <SectionHeader
          title="Custom Evaluations"
          description="Aggregated results from custom evaluators attached to this evaluation run"
        />

        {/* AI Narrative */}
        {report.narrative && (
          <div className="mb-8">
            <h3 className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold mb-3">
              AI Analysis
            </h3>
            <CustomNarrative narrative={report.narrative} />
          </div>
        )}

        {/* Per-evaluator cards */}
        <div className="space-y-6">
          {report.evaluatorSections.map((section) => (
            <EvaluatorCard key={section.evaluatorId} section={section} />
          ))}
        </div>
      </section>
    </div>
  );
}
