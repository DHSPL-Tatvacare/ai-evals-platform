import type { ReactNode } from 'react';
import { cn } from '@/utils';
import { PageHeaderSearch } from './PageHeaderSearch';

export interface TableToolbarSearch {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  label?: string;
  expandedWidth?: number;
}

interface TableToolbarProps {
  search?: TableToolbarSearch;
  filters?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

/**
 * Standard table-page toolbar: search + filters on the left, action buttons
 * on the right. Sits directly above a DataTable inside a fixed-height
 * container so the table area stays constant across pages.
 */
export function TableToolbar({ search, filters, actions, className }: TableToolbarProps) {
  const left = search || filters;
  const right = actions;
  if (!left && !right) return null;
  return (
    <div className={cn('flex items-center justify-between gap-2', className)}>
      <div className="flex items-center gap-2">
        {search ? (
          <PageHeaderSearch
            value={search.value}
            onChange={search.onChange}
            placeholder={search.placeholder}
            label={search.label ?? search.placeholder ?? 'Search'}
            expandedWidth={search.expandedWidth}
          />
        ) : null}
        {filters}
      </div>
      {right ? <div className="flex items-center gap-2">{right}</div> : null}
    </div>
  );
}
