import { useMemo, useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/Button';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import { DataTable, type ColumnDef } from '@/components/ui/DataTable';
import { Input } from '@/components/ui/Input';
import { TableToolbar } from '@/components/ui/TableToolbar';
import { type CrmGrainSchema } from '@/services/api/crmSource';
import { slotTypeOf, useCrmMappingDraftStore } from '@/stores/crmMappingDraftStore';

const FIELDS_PER_PAGE = 25;

const SLOT_TYPE_LABELS: Array<[string, string]> = [
  ['text', 'Custom · Text'],
  ['num', 'Custom · Number'],
  ['int', 'Custom · Whole number'],
  ['dt', 'Custom · Date / time'],
  ['bool', 'Custom · Yes / No'],
  ['json', 'Custom · Structured'],
];

/** Client-side search + paging over the discovered field list. The mapping draft (Zustand) is
 *  never touched here, so bindings survive search and page changes. */
function useFilteredFields(fields: string[]) {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? fields.filter((f) => f.toLowerCase().includes(q)) : fields;
  }, [fields, search]);

  // Reset to page 1 when the search or field set changes — adjust during render, not in an effect.
  const [resetKey, setResetKey] = useState({ search, fields });
  if (resetKey.search !== search || resetKey.fields !== fields) {
    setResetKey({ search, fields });
    setPage(1);
  }

  const totalPages = Math.max(1, Math.ceil(filtered.length / FIELDS_PER_PAGE));
  const page1 = Math.min(page, totalPages);

  return {
    search,
    setSearch,
    page: page1,
    setPage,
    totalPages,
    total: filtered.length,
    pageItems: filtered.slice((page1 - 1) * FIELDS_PER_PAGE, page1 * FIELDS_PER_PAGE),
  };
}

function targetOptionsFor(grain: CrmGrainSchema): ComboboxOption[] {
  return [
    { value: 'ignore', label: "Don't map" },
    ...grain.standardColumns.map((c) => ({ value: `std:${c.target}`, label: c.label, meta: 'Standard' })),
    ...SLOT_TYPE_LABELS.filter(([t]) => (grain.slots[t]?.length ?? 0) > 0).map(([t, label]) => ({
      value: `slot:${t}`,
      label,
      meta: 'Custom field',
    })),
  ];
}

interface Binding {
  targetKind: 'standard' | 'slot' | 'ignore';
  target: string;
  semanticKey: string;
  valueMap: Record<string, string> | null;
}

function targetValueOf(binding: Binding | undefined): string {
  if (!binding) return 'ignore';
  if (binding.targetKind === 'standard') return `std:${binding.target}`;
  if (binding.targetKind === 'slot') return `slot:${slotTypeOf(binding.target) ?? 'text'}`;
  return 'ignore';
}

function TargetCell({ field, grain, options }: { field: string; grain: CrmGrainSchema; options: ComboboxOption[] }) {
  const binding = useCrmMappingDraftStore((s) => s.bindings[field]);
  const setTargetStandard = useCrmMappingDraftStore((s) => s.setTargetStandard);
  const setTargetSlot = useCrmMappingDraftStore((s) => s.setTargetSlot);
  const setIgnore = useCrmMappingDraftStore((s) => s.setIgnore);

  function onChange(value: string) {
    if (value === 'ignore') return setIgnore(field);
    if (value.startsWith('std:')) {
      const col = grain.standardColumns.find((c) => c.target === value.slice(4));
      return col ? setTargetStandard(field, col) : undefined;
    }
    if (value.startsWith('slot:')) return setTargetSlot(field, value.slice(5));
  }

  return (
    <Combobox options={options} value={targetValueOf(binding)} onChange={onChange} size="sm" placeholder="Don't map" />
  );
}

function NameCell({ field }: { field: string }) {
  const binding = useCrmMappingDraftStore((s) => s.bindings[field]);
  const setSemanticKey = useCrmMappingDraftStore((s) => s.setSemanticKey);
  if (!binding) return <span className="text-[var(--text-muted)]">—</span>;
  if (binding.targetKind === 'slot') {
    return (
      <Input
        value={binding.semanticKey}
        onChange={(e) => setSemanticKey(field, e.target.value)}
        placeholder="Field name"
      />
    );
  }
  return <span className="text-[13px] text-[var(--text-secondary)]">{binding.semanticKey}</span>;
}

function ValuesCell({ field }: { field: string }) {
  const binding = useCrmMappingDraftStore((s) => s.bindings[field]);
  const openValueMap = useCrmMappingDraftStore((s) => s.openValueMap);
  if (!binding) return null;
  const count = binding.valueMap ? Object.keys(binding.valueMap).length : 0;
  return (
    <Button variant="ghost" size="sm" onClick={() => openValueMap(field)}>
      {count > 0 ? `Values · ${count}` : 'Values'}
    </Button>
  );
}

interface FieldRow {
  field: string;
}

export function MappingFieldsTable({
  grain,
  fields,
  boundCount,
  loading,
  headerActions,
  footerActions,
}: {
  grain: CrmGrainSchema;
  fields: string[];
  boundCount: number;
  loading: boolean;
  headerActions?: ReactNode;
  footerActions?: ReactNode;
}) {
  const { search, setSearch, page, setPage, totalPages, total, pageItems } = useFilteredFields(fields);
  const options = useMemo(() => targetOptionsFor(grain), [grain]);

  const columns: ColumnDef<FieldRow>[] = [
    {
      key: 'field',
      header: 'CRM field',
      render: (r) => <span className="font-mono text-[12px] text-[var(--text-primary)]">{r.field}</span>,
    },
    { key: 'target', header: 'Maps to', width: 'w-[240px]', render: (r) => <TargetCell field={r.field} grain={grain} options={options} /> },
    { key: 'name', header: 'Name', width: 'w-[200px]', render: (r) => <NameCell field={r.field} /> },
    { key: 'values', header: 'Values', width: 'w-[110px]', render: (r) => <ValuesCell field={r.field} /> },
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <TableToolbar
        search={{ value: search, onChange: setSearch, placeholder: 'Search CRM fields…', label: 'Search CRM fields' }}
        actions={
          <div className="flex items-center gap-3">
            <span className="whitespace-nowrap text-[12px] text-[var(--text-secondary)]">
              {boundCount} mapped · {total} fields
            </span>
            {headerActions}
          </div>
        }
      />
      <div className="flex min-h-0 flex-1 flex-col">
        <DataTable<FieldRow>
          data={pageItems.map((f) => ({ field: f }))}
          columns={columns}
          keyExtractor={(r) => r.field}
          loading={loading}
          minWidth="640px"
          emptyTitle={search ? 'No matching fields' : 'No fields'}
          emptyDescription={search ? 'Try a different search term.' : 'This object exposes no fields to map.'}
          pagination={{ page, totalPages, onPageChange: setPage, pageSize: FIELDS_PER_PAGE, totalItems: total, showCount: true }}
          footerActions={footerActions}
        />
      </div>
    </div>
  );
}
