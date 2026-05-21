import { useEffect, useMemo } from 'react';
import { RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import type { ProviderTemplateSummary } from '@/services/api/orchestrationConnections';
import { useWatiTemplates } from '@/features/orchestration/queries/referenceData';

interface Props {
  /** WATI connection UUID. The picker is disabled until a connection is selected. */
  connectionId?: string;
  value: string;
  onChange(next: string): void;
  /** Fired whenever the operator selects a template (or the cached value resolves on mount).
   *  The inspector consumes this to rebuild the variable-mapping editor's parameter slots. */
  onTemplateLoaded?(template: ProviderTemplateSummary | null): void;
}

/** WATI template picker backed by TanStack Query.
 *  Two pickers on the same connection share one query; reopening within 30 s reuses cache. */
export function WatiTemplatePicker({
  connectionId,
  value,
  onChange,
  onTemplateLoaded,
}: Props) {
  const { data, isFetching, error, refresh } = useWatiTemplates(connectionId);

  const items: ProviderTemplateSummary[] = useMemo(() => data?.items ?? [], [data]);
  const errorMessage =
    error instanceof Error
      ? error.message
      : data?.error
        ? data.error
        : null;

  useEffect(() => {
    if (!onTemplateLoaded) return;
    if (!value) {
      onTemplateLoaded(null);
      return;
    }
    const match = items.find((t) => t.name === value) ?? null;
    onTemplateLoaded(match);
  }, [items, value, onTemplateLoaded]);

  const options: ComboboxOption[] = items.map((t) => ({
    value: t.name,
    label: t.name,
    meta: t.language || t.status,
  }));

  if (!connectionId) {
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        Pick a WATI connection above to load available templates.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <Combobox
            options={options}
            value={value}
            onChange={onChange}
            placeholder={isFetching ? 'Loading templates…' : 'Select a template'}
            disabled={isFetching && items.length === 0}
            loading={isFetching}
          />
        </div>
        <Button
          variant="secondary"
          size="sm"
          icon={RefreshCw}
          onClick={() => void refresh()}
          disabled={isFetching}
          aria-label="Refresh templates"
          className="shrink-0 whitespace-nowrap"
        >
          Refresh
        </Button>
      </div>
      {errorMessage && (
        <p className="text-xs text-[var(--color-error)]">{errorMessage}</p>
      )}
      {!isFetching && !errorMessage && items.length === 0 && (
        <p className="text-xs text-[var(--text-secondary)]">
          No templates found. Approve a template in WATI and click Refresh.
        </p>
      )}
    </div>
  );
}
