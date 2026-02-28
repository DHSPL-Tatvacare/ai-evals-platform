import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { AdversarialBreakdown as AdversarialBreakdownType } from '@/types/reports';
import SectionHeader from './shared/SectionHeader';
import { DIFFICULTY_COLORS, METRIC_HEX } from './shared/colors';
import { useResolvedColor } from '@/hooks/useResolvedColor';

interface Props {
  adversarial: AdversarialBreakdownType;
}

export default function AdversarialBreakdown({ adversarial }: Props) {
  const gridColor = useResolvedColor('var(--border-subtle)');
  const textColor = useResolvedColor('var(--text-muted)');
  const tooltipBg = useResolvedColor('var(--bg-elevated)');
  const tooltipBorder = useResolvedColor('var(--border-default)');

  const sortedCategories = [...adversarial.byCategory].sort((a, b) => a.passRate - b.passRate);

  const chartData = sortedCategories.map((cat) => ({
    name: cat.category,
    passed: cat.passed,
    failed: cat.total - cat.passed,
    rate: Math.round(cat.passRate * 100),
  }));

  const difficultyOrder = ['EASY', 'MEDIUM', 'HARD'];
  const sortedDifficulty = [...adversarial.byDifficulty].sort(
    (a, b) => difficultyOrder.indexOf(a.difficulty) - difficultyOrder.indexOf(b.difficulty),
  );

  return (
    <section>
      <SectionHeader
        title="Adversarial Testing Results"
        description="How the bot handled adversarial test scenarios by category and difficulty"
      />

      {chartData.length > 0 && (
        <div className="mb-6">
          <h4 className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold mb-3">
            Pass Rate by Category
          </h4>
          <div className="bg-[var(--bg-primary)] rounded border border-[var(--border-subtle)] p-3">
            <ResponsiveContainer width="100%" height={Math.max(chartData.length * 45, 120)}>
              <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11, fill: textColor }} allowDecimals={false} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: textColor }} width={140} />
                <Tooltip contentStyle={{ fontSize: 12, backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}` }} />
                <Bar dataKey="passed" stackId="a" fill="#10B981" radius={[0, 0, 0, 0]} />
                <Bar dataKey="failed" stackId="a" fill="#EF4444" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 px-1">
              {chartData.map((entry) => (
                <span key={entry.name} className="text-xs text-[var(--text-secondary)]">
                  {entry.name}: <span className="font-semibold">{entry.passed}/{entry.passed + entry.failed}</span>{' '}
                  <span className="text-[var(--text-muted)]">({entry.rate}%)</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Compact inline stat row for difficulty */}
      {sortedDifficulty.length > 0 && (
        <div className="flex items-center gap-6 py-2 mt-4 text-sm">
          {sortedDifficulty.map((d) => {
            const rate = d.total > 0 ? Math.round((d.passed / d.total) * 100) : 0;
            return (
              <div key={d.difficulty}>
                <span className="text-[var(--text-muted)] text-xs">{d.difficulty}</span>
                <span
                  className="font-bold ml-1"
                  style={{ color: DIFFICULTY_COLORS[d.difficulty] ?? METRIC_HEX(rate) }}
                >
                  {rate}%
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
