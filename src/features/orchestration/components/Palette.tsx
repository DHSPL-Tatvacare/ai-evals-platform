import { useEffect } from 'react';

import { fetchNodeTypes } from '@/services/api/orchestration';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import { PaletteItem } from './PaletteItem';

const CATEGORIES: Array<{ key: string; label: string }> = [
  { key: 'source', label: 'Source' },
  { key: 'filter', label: 'Filter' },
  { key: 'logic', label: 'Logic' },
  { key: 'action', label: 'Action' },
  { key: 'escalation', label: 'Escalation' },
  { key: 'sink', label: 'Sink' },
];

export function Palette() {
  const workflowType = useWorkflowBuilderStore((s) => s.workflowType);
  const palette = useWorkflowBuilderStore((s) => s.paletteCatalog);
  const setCatalog = useWorkflowBuilderStore((s) => s.setPaletteCatalog);
  const setLoading = useWorkflowBuilderStore((s) => s.setPaletteLoading);

  useEffect(() => {
    if (!workflowType) return;
    let alive = true;
    setLoading(true);
    fetchNodeTypes(workflowType)
      .then((catalog) => {
        if (alive) setCatalog(catalog);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [workflowType, setCatalog, setLoading]);

  return (
    <div className="flex h-full w-64 flex-col gap-3 overflow-y-auto border-r border-[var(--border-default)] p-3">
      {CATEGORIES.map((c) => {
        const items = palette.filter((p) => p.category === c.key);
        if (items.length === 0) return null;
        return (
          <div key={c.key}>
            <div className="mb-1 text-xs font-semibold uppercase text-[var(--text-secondary)]">
              {c.label}
            </div>
            <div className="flex flex-col gap-1">
              {items.map((d) => (
                <PaletteItem key={`${d.workflowType}-${d.nodeType}`} desc={d} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
