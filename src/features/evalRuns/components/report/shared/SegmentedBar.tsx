import { cn } from '@/utils/cn';

export interface BarSegment {
  label: string;
  value: number;
  color: string;
}

interface Props {
  segments: BarSegment[];
  /** Tailwind height class for the bar. Default: 'h-7' */
  barHeight?: string;
  /** Show values inside bar segments. Default: true */
  showValues?: boolean;
  /** Format the value shown inside a segment and in the legend. */
  formatValue?: (value: number) => string;
  /** When false, legend shows just the label without appending ": value". Default: true */
  showLegendValues?: boolean;
  className?: string;
}

export default function SegmentedBar({
  segments,
  barHeight = 'h-7',
  showValues = true,
  formatValue = (v) => String(Math.round(v)),
  showLegendValues = true,
  className,
}: Props) {
  const filtered = segments.filter((s) => s.value > 0);
  const total = filtered.reduce((sum, s) => sum + s.value, 0);
  if (total === 0) return null;

  return (
    <div className={className}>
      <div className={cn('flex rounded-md overflow-hidden', barHeight)}>
        {filtered.map((seg) => (
          <div
            key={seg.label}
            className="flex items-center justify-center text-[11px] font-bold text-white min-w-[20px]"
            style={{ flex: seg.value, backgroundColor: seg.color }}
            title={`${seg.label}: ${formatValue(seg.value)}`}
          >
            {showValues && seg.value / total >= 0.08 ? formatValue(seg.value) : null}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-3 mt-2">
        {filtered.map((seg) => (
          <div key={seg.label} className="flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)]">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: seg.color }} />
            {showLegendValues ? `${seg.label}: ${formatValue(seg.value)}` : seg.label}
          </div>
        ))}
      </div>
    </div>
  );
}
