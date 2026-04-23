import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/utils';
import { Select } from './Select';

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  showCount?: boolean;
  totalItems?: number;
  pageSize?: number;
  pageSizeOptions?: number[];
  onPageSizeChange?: (size: number) => void;
  className?: string;
}

const DEFAULT_PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

type PageSlot = number | 'ellipsis';

/**
 * Compact pagination window:
 *   1 · 2 · 3 · … · 7 · [8] · 9 · … · 41 · 42
 *
 * Always shows first + last, current ± `neighbours`, and an ellipsis anywhere
 * those blocks aren't adjacent. For small page counts it returns every page.
 * Pure, side-effect-free so it's cheap to run on every render.
 */
function buildPageWindow(current: number, total: number, neighbours = 1): PageSlot[] {
  if (total <= 0) return [];
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);

  const first = 1;
  const last = total;
  const windowStart = Math.max(first + 1, current - neighbours);
  const windowEnd = Math.min(last - 1, current + neighbours);

  const slots: PageSlot[] = [first];
  if (windowStart > first + 1) slots.push('ellipsis');
  for (let p = windowStart; p <= windowEnd; p += 1) slots.push(p);
  if (windowEnd < last - 1) slots.push('ellipsis');
  slots.push(last);
  return slots;
}

export function Pagination({
  page,
  totalPages,
  onPageChange,
  showCount = false,
  totalItems,
  pageSize,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
  onPageSizeChange,
  className,
}: PaginationProps) {
  const hasSizeSelector = !!onPageSizeChange && pageSize != null;
  const hasCount = showCount && totalItems != null && pageSize != null;

  if (totalPages <= 1 && !hasSizeSelector && !hasCount) return null;

  const sizeOptions = pageSizeOptions.map((n) => ({ value: String(n), label: `${n} / page` }));
  // Windowed pagination: always show first + last, current ± 1 neighbour, with
  // `…` between non-adjacent blocks. Pure computation so no branching in JSX.
  const pages = buildPageWindow(page, totalPages);

  return (
    <div className={cn('flex items-center gap-3', className)}>
      {totalPages > 1 && (
        <div className="flex items-center gap-1">
          <button
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="p-1 rounded text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-30 disabled:pointer-events-none transition-colors"
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          {pages.map((p, i) =>
            p === 'ellipsis' ? (
              <span
                key={`ellipsis-${i}`}
                className="px-1 text-xs text-[var(--text-muted)] select-none"
                aria-hidden
              >
                …
              </span>
            ) : (
              <button
                key={p}
                onClick={() => onPageChange(p)}
                aria-current={page === p ? 'page' : undefined}
                className={cn(
                  'min-w-[28px] h-7 px-1.5 text-xs font-medium rounded transition-colors tabular-nums',
                  page === p
                    ? 'bg-[var(--interactive-primary)] text-[var(--text-on-color)]'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]',
                )}
              >
                {p}
              </button>
            ),
          )}

          <button
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="p-1 rounded text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-30 disabled:pointer-events-none transition-colors"
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {hasSizeSelector && (
        <Select
          size="sm"
          value={String(pageSize)}
          onChange={(v) => onPageSizeChange(Number(v))}
          options={sizeOptions}
          className="w-[110px]"
        />
      )}
      {hasCount && ((totalItems as number) > 0 ? (
        <p className="text-[12px] text-[var(--text-muted)]">
          Showing {(page - 1) * (pageSize as number) + 1}&ndash;
          {Math.min(page * (pageSize as number), totalItems as number)} of {totalItems}
        </p>
      ) : (
        <p className="text-[12px] text-[var(--text-muted)]">No results</p>
      ))}
    </div>
  );
}
