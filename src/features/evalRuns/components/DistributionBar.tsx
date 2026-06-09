import { getVerdictColor, getLabelDefinition } from '@/config/labelDefinitions';
import { normalizeLabel } from '@/utils/evalFormatters';
import { cn } from '@/utils/cn';

interface Props {
  distribution: Record<string, number>;
  aiDistribution?: Record<string, number>;
  order?: readonly string[];
}

type NormalizedMap = Map<string, { count: number; raw: string }>;

function normalizeDistribution(dist: Record<string, number>): NormalizedMap {
  const normalized: NormalizedMap = new Map();
  for (const [raw, count] of Object.entries(dist)) {
    if (count <= 0) continue;
    const n = normalizeLabel(raw);
    const existing = normalized.get(n);
    normalized.set(n, {
      count: (existing?.count ?? 0) + count,
      raw: existing?.raw ?? raw,
    });
  }
  return normalized;
}

function resolveOrderedKeys(normalizedDist: NormalizedMap, order?: readonly string[]): string[] {
  return order
    ? order.map((k) => normalizeLabel(k)).filter((k) => normalizedDist.has(k))
    : Array.from(normalizedDist.keys());
}

function BarSegments({
  normalizedDist,
  orderedKeys,
  total,
  faded,
}: {
  normalizedDist: NormalizedMap;
  orderedKeys: string[];
  total: number;
  faded?: boolean;
}) {
  return (
    <div className={cn('flex h-6 rounded overflow-hidden bg-[var(--bg-tertiary)]', faded && 'opacity-35')}>
      {orderedKeys.map((key) => {
        const entry = normalizedDist.get(key)!;
        const widthPct = (entry.count / total) * 100;
        return (
          <div
            key={key}
            className="flex items-center justify-center text-[0.64rem] font-semibold text-[var(--text-on-color)] min-w-[18px] cursor-default transition-opacity hover:opacity-85"
            style={{
              width: `${widthPct}%`,
              backgroundColor: getVerdictColor(key),
            }}
            title={`${key}: ${entry.count} (${Math.round(widthPct)}%)`}
          >
            {widthPct > 8 ? entry.count : ''}
          </div>
        );
      })}
    </div>
  );
}

function Legend({
  normalizedDist,
  orderedKeys,
  aiNormalizedDist,
}: {
  normalizedDist: NormalizedMap;
  orderedKeys: string[];
  aiNormalizedDist?: NormalizedMap;
}) {
  return (
    <div className="flex gap-3 mt-1 flex-wrap">
      {orderedKeys.map((key) => {
        const entry = normalizedDist.get(key)!;
        const def = getLabelDefinition(key, 'correctness');
        const displayName = def.description !== 'Unknown label' ? def.displayName : key;
        const aiCount = aiNormalizedDist?.get(key)?.count;
        const delta = aiCount != null ? entry.count - aiCount : undefined;
        return (
          <div key={key} className="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
            <span
              className="w-1.5 h-1.5 rounded-full inline-block"
              style={{ backgroundColor: getVerdictColor(key) }}
            />
            {displayName}: {entry.count}
            {delta != null && delta !== 0 && (
              <span className="text-[var(--color-success)] font-semibold ml-0.5">
                ({delta > 0 ? '+' : ''}{delta})
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function DistributionBar({ distribution, aiDistribution, order }: Props) {
  const total = Object.values(distribution).reduce((a, b) => a + b, 0);
  if (total === 0) {
    return (
      <div className="h-6 rounded bg-[var(--bg-tertiary)] flex items-center justify-center text-xs text-[var(--text-muted)]">
        No data
      </div>
    );
  }

  const normalizedDist = normalizeDistribution(distribution);
  const orderedKeys = resolveOrderedKeys(normalizedDist, order);

  if (!aiDistribution) {
    return (
      <div>
        <BarSegments normalizedDist={normalizedDist} orderedKeys={orderedKeys} total={total} />
        <Legend normalizedDist={normalizedDist} orderedKeys={orderedKeys} />
      </div>
    );
  }

  const aiNormalizedDist = normalizeDistribution(aiDistribution);
  const aiTotal = Object.values(aiDistribution).reduce((a, b) => a + b, 0);
  const aiOrderedKeys = resolveOrderedKeys(aiNormalizedDist, order);

  return (
    <div>
      <BarSegments normalizedDist={aiNormalizedDist} orderedKeys={aiOrderedKeys} total={aiTotal} faded />
      <div className="text-[0.6rem] text-[var(--text-muted)] my-0.5">↓ human-adjusted</div>
      <BarSegments normalizedDist={normalizedDist} orderedKeys={orderedKeys} total={total} />
      <Legend normalizedDist={normalizedDist} orderedKeys={orderedKeys} aiNormalizedDist={aiNormalizedDist} />
    </div>
  );
}
