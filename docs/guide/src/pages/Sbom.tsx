import { useState } from 'react';
import { FilterPills, DataTable, InfoBox, ExportButton, Badge } from '@/components';
import { usePageExport } from '@/hooks/usePageExport';
import { sbomData, sbomCategories, type SbomEntry } from '@/data/sbom';

const categoryColorMap: Record<string, 'blue' | 'green' | 'purple' | 'amber' | 'red'> = {
  Frontend: 'blue',
  Backend: 'green',
  Database: 'amber',
  Infrastructure: 'purple',
  'Dev Tooling': 'red',
};

const filterOptions = sbomCategories.map((c) => ({ id: c, label: c }));

const columns = [
  {
    key: 'name' as const,
    header: 'Package',
    render: (val: unknown) => (
      <code style={{ color: 'var(--accent-text)', fontSize: '0.8125rem' }}>{String(val)}</code>
    ),
  },
  {
    key: 'version' as const,
    header: 'Version',
    render: (val: unknown) => (
      <code style={{ fontSize: '0.8125rem' }}>{String(val)}</code>
    ),
  },
  {
    key: 'license' as const,
    header: 'License',
    render: (val: unknown) => (
      <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{String(val)}</span>
    ),
  },
  {
    key: 'category' as const,
    header: 'Category',
    render: (val: unknown) => {
      const cat = String(val);
      return <Badge color={categoryColorMap[cat] ?? 'blue'}>{cat}</Badge>;
    },
  },
  {
    key: 'description' as const,
    header: 'Description',
    wrap: true,
  },
];

export default function Sbom() {
  const [activeFilter, setActiveFilter] = useState('All');
  const { contentRef } = usePageExport();

  const filtered = activeFilter === 'All'
    ? sbomData
    : sbomData.filter((e) => e.category === activeFilter);

  return (
    <div ref={contentRef} className="page-content animate-fade-in-up" data-title="SBOM">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-2xl font-bold" style={{ color: 'var(--text)' }}>
          Software Bill of Materials
        </h2>
        <ExportButton pageTitle="SBOM" contentRef={contentRef} />
      </div>

      <InfoBox className="mb-4">
        Full inventory of {sbomData.length} packages and services used across the AI Evals Platform.
        Filter by category to explore the stack. Versions reflect the current project configuration.
      </InfoBox>

      <FilterPills options={filterOptions} active={activeFilter} onChange={setActiveFilter} />

      <p className="text-sm mb-2" style={{ color: 'var(--text-secondary)' }}>
        Showing {filtered.length} of {sbomData.length} entries
      </p>

      <DataTable<SbomEntry> columns={columns} data={filtered} />
    </div>
  );
}
