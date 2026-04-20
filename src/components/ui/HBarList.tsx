import type { CSSProperties, ReactNode } from 'react';
import { cn } from '@/utils';

export type HBarTone =
  | 'accent'
  | 'success'
  | 'warning'
  | 'error'
  | 'neutral'
  | 'app:voicerx'
  | 'app:kaira'
  | 'app:insidesales'
  | 'app:report'
  | 'app:system'
  | 'purpose:purple'
  | 'purpose:purple-light'
  | 'purpose:blue'
  | 'purpose:blue-light'
  | 'purpose:orange'
  | 'purpose:green'
  | 'purpose:gray'
  | 'purpose:gray-light';

const TONE_COLOR: Record<HBarTone, string> = {
  accent: 'var(--color-brand-primary)',
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  error: 'var(--color-error)',
  neutral: 'var(--text-muted)',
  'app:voicerx': 'var(--color-app-voicerx)',
  'app:kaira': 'var(--color-app-kaira)',
  'app:insidesales': 'var(--color-app-insidesales)',
  'app:report': 'var(--color-app-report)',
  'app:system': 'var(--color-app-system)',
  'purpose:purple': 'var(--color-purpose-purple)',
  'purpose:purple-light': 'var(--color-purpose-purple-light)',
  'purpose:blue': 'var(--color-purpose-blue)',
  'purpose:blue-light': 'var(--color-purpose-blue-light)',
  'purpose:orange': 'var(--color-purpose-orange)',
  'purpose:green': 'var(--color-purpose-green)',
  'purpose:gray': 'var(--color-purpose-gray)',
  'purpose:gray-light': 'var(--color-purpose-gray-light)',
};

export interface HBarRowData {
  key: string;
  /** Node rendered in the name column. Accepts strings, tags, etc. */
  label: ReactNode;
  /** 0..1 fraction for the track fill. */
  pct: number;
  tone?: HBarTone;
  /** Primary right-column amount (e.g. `$1,234` or `12.3M tok`). */
  amount?: ReactNode;
  /** Optional trailing meta (e.g. `43%`, `saved $204`). */
  meta?: ReactNode;
  metaTone?: 'neutral' | 'muted' | 'success' | 'warning' | 'error';
}

interface HBarListProps {
  rows: HBarRowData[];
  className?: string;
  /** CSS grid template for each row (override default 4-col layout). */
  columnsTemplate?: string;
}

const META_TONE: Record<NonNullable<HBarRowData['metaTone']>, string> = {
  neutral: 'text-[var(--text-secondary)]',
  muted: 'text-[var(--text-muted)]',
  success: 'text-[var(--color-success)]',
  warning: 'text-[var(--color-warning)]',
  error: 'text-[var(--color-error)]',
};

export function HBarList({ rows, className, columnsTemplate }: HBarListProps) {
  if (!rows.length) {
    return (
      <p className={cn('py-6 text-center text-xs text-[var(--text-muted)]', className)}>
        No data
      </p>
    );
  }
  const template = columnsTemplate ?? 'minmax(0, 1fr) minmax(0, 2fr) minmax(6ch, auto) minmax(4ch, auto)';
  return (
    <div className={cn('flex flex-col', className)}>
      {rows.map((row, i) => {
        const fillColor = TONE_COLOR[row.tone ?? 'accent'];
        const width = Math.max(0, Math.min(1, row.pct)) * 100;
        const rowStyle: CSSProperties = { gridTemplateColumns: template };
        return (
          <div
            key={row.key}
            className={cn(
              'grid items-center gap-2.5 py-2 text-[12.5px]',
              i !== 0 && 'border-t border-dashed border-[var(--border-subtle)]',
            )}
            style={rowStyle}
          >
            <div className="min-w-0 truncate font-medium text-[var(--text-primary)]">
              {row.label}
            </div>
            <div className="relative h-2 rounded-[4px] bg-[var(--bg-tertiary)]">
              <div
                className="absolute inset-y-0 left-0 rounded-[4px]"
                style={{ width: `${width}%`, background: fillColor }}
              />
            </div>
            <div className="text-right tabular-nums text-[var(--text-primary)]">
              {row.amount ?? null}
            </div>
            <div
              className={cn(
                'text-right tabular-nums text-[11.5px]',
                META_TONE[row.metaTone ?? 'muted'],
              )}
            >
              {row.meta ?? null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
