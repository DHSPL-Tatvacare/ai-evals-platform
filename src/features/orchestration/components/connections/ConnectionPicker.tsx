import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import { useOrchestrationRoutes } from '@/features/orchestration/hooks/useOrchestrationRoutes';
import {
  listConnections,
  type Connection,
} from '@/services/api/orchestrationConnections';

interface BasePickerProps {
  appId: string;
  value: string;
  onChange(connectionId: string): void;
  disabled?: boolean;
  /** Surfaced in the empty-state link copy. Falls back to the resolved
   *  connections route when omitted. */
  emptyCreateRoute?: string;
}

interface SingleProviderProps extends BasePickerProps {
  provider: string;
  providers?: never;
}

interface MultiProviderProps extends BasePickerProps {
  provider?: never;
  providers: readonly string[];
}

export type ConnectionPickerProps = SingleProviderProps | MultiProviderProps;

/** Small, fully token-styled wrapper around `Combobox` that lists active
 *  tenant connections filtered by provider (single or multi). When the
 *  list is empty an inline link routes the operator to the connections
 *  page so they can create one without losing their place. */
export function ConnectionPicker(props: ConnectionPickerProps) {
  const { appId, value, onChange, disabled, emptyCreateRoute } = props;
  const orchestrationRoutes = useOrchestrationRoutes();
  const providers = useMemo<readonly string[]>(() => {
    if ('providers' in props && props.providers) return props.providers;
    if ('provider' in props && props.provider) return [props.provider];
    return [];
  }, [props]);

  const [rows, setRows] = useState<Connection[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setError(null);
    setRows(null);
    listConnections({
      appId,
      providers: providers.length > 0 ? Array.from(providers) : undefined,
    })
      .then((result) => {
        if (!alive) return;
        setRows(result);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(err instanceof Error ? err.message : 'Failed to load connections');
        setRows([]);
      });
    return () => {
      alive = false;
    };
  }, [appId, providers]);

  const options: ComboboxOption[] = useMemo(() => {
    if (!rows) return [];
    return rows.map((c) => ({
      value: c.id,
      label: c.name,
      meta: c.provider,
      searchText: `${c.provider} ${c.name}`,
    }));
  }, [rows]);

  const createRoute = emptyCreateRoute ?? orchestrationRoutes.connections;
  const placeholder =
    rows === null ? 'Loading…' : 'Select a connection…';

  return (
    <div className="flex flex-col gap-1">
      <Combobox
        value={value}
        onChange={onChange}
        options={options}
        placeholder={placeholder}
        disabled={disabled || rows === null}
      />
      {rows && rows.length === 0 ? (
        <p className="text-xs text-[var(--text-secondary)]">
          No active{' '}
          {providers.length === 1 ? (
            <span className="font-medium">{providers[0]}</span>
          ) : (
            'matching'
          )}{' '}
          connections.{' '}
          <Link
            to={createRoute}
            className="text-[var(--text-brand)] underline underline-offset-2"
          >
            + New Connection
          </Link>
        </p>
      ) : null}
      {error ? (
        <p className="text-xs text-[var(--color-error)]">{error}</p>
      ) : null}
    </div>
  );
}
