import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Layers, Trash2 } from 'lucide-react';
import { Button, Combobox, DataTable, ProviderTag, type ColumnDef, type ComboboxOption } from '@/components/ui';
import { notificationService } from '@/services/notifications';
import { costApi } from '@/services/api/costApi';
import { usePermission } from '@/utils/permissions';
import { useCostStore } from '@/stores/costStore';
import { formatDateTime, formatInt } from '../utils/format';
import type { AliasRow, CatalogRow, UnmappedModelRow } from '../types';

interface TabProps {
  active: boolean;
}

interface UnmappedRowState extends UnmappedModelRow {
  selectedCanonical: string;
  busy: boolean;
}

export function UnmappedTab({ active }: TabProps) {
  const canEdit = usePermission('cost:edit');
  const pricing = useCostStore((s) => s.pricing);
  const loadPricing = useCostStore((s) => s.loadPricing);

  const [unmapped, setUnmapped] = useState<UnmappedRowState[]>([]);
  const [aliases, setAliases] = useState<AliasRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [u, a] = await Promise.all([
        costApi.fetchUnmappedModels(),
        costApi.fetchAliases(),
      ]);
      setUnmapped(
        u.rows.map((r) => ({
          ...r,
          selectedCanonical: r.suggestedCanonical ?? '',
          busy: false,
        })),
      );
      setAliases(a.aliases);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load unmapped models');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!active) return;
    void load();
    // Keep catalog warm for the canonical dropdown; costStore's pricing slice
    // carries the catalog bundle used by the Pricing tab.
    if (!pricing.data) void loadPricing();
  }, [active, load, pricing.data, loadPricing]);

  const catalogByProvider = useMemo<Record<string, CatalogRow[]>>(() => {
    const bucket: Record<string, CatalogRow[]> = {};
    for (const c of pricing.data?.catalog ?? []) {
      (bucket[c.provider] ??= []).push(c);
    }
    return bucket;
  }, [pricing.data]);

  const catalogOptionsFor = useCallback(
    (provider: string): ComboboxOption[] =>
      (catalogByProvider[provider] ?? []).map((c) => ({
        value: c.model,
        label: c.displayName || c.model,
        searchText: `${c.model} ${c.displayName ?? ''} ${c.family ?? ''}`,
        meta: c.family || undefined,
      })),
    [catalogByProvider],
  );

  const handleCanonicalChange = useCallback((rowKey: string, value: string) => {
    setUnmapped((prev) =>
      prev.map((r) =>
        `${r.provider}:${r.model}` === rowKey ? { ...r, selectedCanonical: value } : r,
      ),
    );
  }, []);

  const handleMap = useCallback(
    async (row: UnmappedRowState) => {
      if (!row.selectedCanonical) {
        notificationService.warning('Pick a canonical model first');
        return;
      }
      const rowKey = `${row.provider}:${row.model}`;
      setUnmapped((prev) => prev.map((r) => (`${r.provider}:${r.model}` === rowKey ? { ...r, busy: true } : r)));
      try {
        const alias = await costApi.upsertAlias({
          provider: row.provider,
          observed: row.model,
          canonical: row.selectedCanonical,
          tenantScope: 'tenant',
        });
        const reprice = await costApi.repriceAlias(alias.id);
        notificationService.success(
          `Mapped ${row.model} → ${row.selectedCanonical} · repriced ${reprice.repriced} row${reprice.repriced === 1 ? '' : 's'}`,
        );
        await load();
      } catch (e) {
        notificationService.error(e instanceof Error ? e.message : 'Failed to map model');
        setUnmapped((prev) => prev.map((r) => (`${r.provider}:${r.model}` === rowKey ? { ...r, busy: false } : r)));
      }
    },
    [load],
  );

  const handleDeleteAlias = useCallback(
    async (alias: AliasRow) => {
      if (!canEdit) return;
      try {
        await costApi.deleteAlias(alias.id);
        notificationService.success(`Removed alias ${alias.observed}`);
        await load();
      } catch (e) {
        notificationService.error(e instanceof Error ? e.message : 'Failed to remove alias');
      }
    },
    [canEdit, load],
  );

  const unmappedColumns: ColumnDef<UnmappedRowState>[] = [
    {
      key: 'provider',
      header: 'Provider',
      width: 'w-32',
      render: (r) => <ProviderTag value={r.provider} />,
    },
    {
      key: 'model',
      header: 'Observed model',
      render: (r) => <span className="font-mono text-[12px] text-[var(--text-primary)]">{r.model}</span>,
    },
    {
      key: 'callCount',
      header: 'Calls',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums',
      headerClassName: 'text-right',
      render: (r) => <span className="text-[12px] text-[var(--text-secondary)]">{formatInt(r.callCount)}</span>,
    },
    {
      key: 'lastSeenAt',
      header: 'Last seen',
      width: 'w-40',
      render: (r) => <span className="text-[12px] text-[var(--text-muted)]">{formatDateTime(r.lastSeenAt)}</span>,
    },
    {
      key: 'canonical',
      header: 'Map to',
      render: (r) => {
        const rowKey = `${r.provider}:${r.model}`;
        return (
          <Combobox
            size="sm"
            options={catalogOptionsFor(r.provider)}
            value={r.selectedCanonical}
            onChange={(v) => handleCanonicalChange(rowKey, v)}
            placeholder="Pick canonical model"
            disabled={!canEdit || r.busy}
            className="w-[260px]"
          />
        );
      },
    },
    {
      key: 'action',
      header: '',
      width: 'w-28',
      cellClassName: 'text-right',
      render: (r) => (
        <Button
          size="sm"
          variant="primary"
          icon={CheckCircle2}
          disabled={!canEdit || !r.selectedCanonical || r.busy}
          isLoading={r.busy}
          onClick={() => handleMap(r)}
        >
          Map
        </Button>
      ),
    },
  ];

  const aliasColumns: ColumnDef<AliasRow>[] = [
    {
      key: 'scope',
      header: 'Scope',
      width: 'w-24',
      render: (r) => (
        <span className="text-[12px] text-[var(--text-secondary)]">
          {r.tenantId === null ? 'System' : 'Tenant'}
        </span>
      ),
    },
    {
      key: 'provider',
      header: 'Provider',
      width: 'w-32',
      render: (r) => <ProviderTag value={r.provider} />,
    },
    {
      key: 'observed',
      header: 'Observed',
      render: (r) => <span className="font-mono text-[12px] text-[var(--text-primary)]">{r.observed}</span>,
    },
    {
      key: 'canonical',
      header: 'Canonical',
      render: (r) => <span className="font-mono text-[12px] text-[var(--text-brand)]">{r.canonical}</span>,
    },
    {
      key: 'updatedAt',
      header: 'Updated',
      width: 'w-40',
      render: (r) => <span className="text-[12px] text-[var(--text-muted)]">{formatDateTime(r.updatedAt)}</span>,
    },
    {
      key: 'action',
      header: '',
      width: 'w-16',
      cellClassName: 'text-right',
      render: (r) => (
        <Button
          size="sm"
          variant="ghost"
          icon={Trash2}
          disabled={!canEdit || (r.tenantId === null)}
          title={r.tenantId === null ? 'System aliases are platform-wide' : 'Remove alias'}
          onClick={() => handleDeleteAlias(r)}
        />
      ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 pb-6">
      <section>
        <header className="mb-2 flex items-center justify-between">
          <div>
            <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">
              Needs mapping
            </h3>
            <p className="text-[12px] text-[var(--text-muted)]">
              Observed models with no pricing match. Pick a canonical model from the models.dev catalog; historical rows are re-priced automatically.
            </p>
          </div>
          {!canEdit && (
            <span className="text-[11px] text-[var(--text-muted)]">
              Requires <code className="font-mono">cost:edit</code> to map
            </span>
          )}
        </header>
        {error ? (
          <div className="rounded border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4 text-[12px] text-[var(--color-danger)]">
            {error}
          </div>
        ) : loading ? (
          <div className="rounded border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4 text-[12px] text-[var(--text-muted)]">
            Loading…
          </div>
        ) : unmapped.length === 0 ? (
          <div className="flex items-center gap-2 rounded border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4 text-[12px] text-[var(--text-muted)]">
            <Layers className="h-4 w-4" />
            <span>No unmapped models — every logged call resolves to a pricing row.</span>
          </div>
        ) : (
          <DataTable<UnmappedRowState>
            data={unmapped}
            columns={unmappedColumns}
            keyExtractor={(r: UnmappedRowState) => `${r.provider}:${r.model}`}
          />
        )}
      </section>

      <section>
        <header className="mb-2">
          <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">Current aliases</h3>
          <p className="text-[12px] text-[var(--text-muted)]">
            Tenant aliases take precedence over system-wide defaults.
          </p>
        </header>
        {aliases.length === 0 ? (
          <div className="rounded border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4 text-[12px] text-[var(--text-muted)]">
            No aliases yet.
          </div>
        ) : (
          <DataTable<AliasRow> data={aliases} columns={aliasColumns} keyExtractor={(r: AliasRow) => r.id} />
        )}
      </section>
    </div>
  );
}
