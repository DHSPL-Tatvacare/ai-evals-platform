import { Card } from '@/components/ui';
import { cn } from '@/utils';
import { formatTokensCompact, formatUsd } from '../utils/format';
import type { ModalityBreakdown } from '../types';

const MODALITY_COLORS: Record<string, string> = {
  text: 'var(--interactive-primary)',
  audio: 'var(--color-info)',
  image: 'var(--color-warning)',
};

function modalityColor(modality: string): string {
  return MODALITY_COLORS[modality.toLowerCase()] ?? 'var(--text-muted)';
}

interface Props {
  data: ModalityBreakdown;
}

export function ModalityStrip({ data }: Props) {
  const { modalities, totalTokens } = data;

  if (totalTokens === 0) {
    return (
      <Card className="p-4">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">By modality</h3>
          <span className="text-[11.5px] text-[var(--text-muted)]">tokens · est. cost</span>
        </div>
        <p className="mt-3 text-[12px] text-[var(--text-muted)]">No usage in range</p>
      </Card>
    );
  }

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">By modality</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">tokens · est. cost</span>
      </div>

      {/* Stacked horizontal bar */}
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-[var(--bg-tertiary)] flex">
        {modalities.map((m) => {
          const pct = (m.tokens / totalTokens) * 100;
          if (pct === 0) return null;
          return (
            <span
              key={m.modality}
              className="block h-full"
              style={{ width: `${pct}%`, backgroundColor: modalityColor(m.modality) }}
            />
          );
        })}
      </div>

      {/* Legend row */}
      <div className={cn('mt-2.5 flex flex-wrap gap-x-5 gap-y-1')}>
        {modalities.map((m) => (
          <span key={m.modality} className="flex items-center gap-1.5 text-[12px]">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: modalityColor(m.modality) }}
            />
            <span className="font-medium text-[var(--text-primary)] capitalize">{m.modality}</span>
            <span className="tabular-nums text-[var(--text-secondary)]">
              {formatTokensCompact(m.tokens)}
            </span>
            <span className="tabular-nums text-[var(--text-secondary)]">
              ~{formatUsd(m.costUsd)}
            </span>
            <span className="text-[10px] text-[var(--text-muted)]">est</span>
          </span>
        ))}
      </div>
    </Card>
  );
}
