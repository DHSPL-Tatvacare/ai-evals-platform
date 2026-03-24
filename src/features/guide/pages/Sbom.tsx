import { useState } from "react";
import { FilterPills, DataTable, Badge, PageHeader } from "@/features/guide/components";
import { usePageExport } from "@/features/guide/hooks/usePageExport";
import { sbomData, sbomCategories, type SbomEntry } from "@/features/guide/data/sbom";

const categoryColorMap: Record<
  string,
  "blue" | "green" | "purple" | "amber" | "red"
> = {
  Frontend: "blue",
  Backend: "green",
  Database: "amber",
  Infrastructure: "purple",
  "Dev Tooling": "red",
};

const filterOptions = sbomCategories.map((c) => ({ id: c, label: c }));

const columns = [
  {
    key: "name" as const,
    header: "Package",
    render: (val: unknown) => (
      <code style={{ color: "var(--accent-text)", fontSize: "0.8125rem" }}>
        {String(val)}
      </code>
    ),
  },
  {
    key: "version" as const,
    header: "Version",
    render: (val: unknown) => (
      <code style={{ fontSize: "0.8125rem" }}>{String(val)}</code>
    ),
  },
  {
    key: "license" as const,
    header: "License",
    render: (val: unknown) => (
      <span
        className="text-xs font-medium"
        style={{ color: "var(--text-secondary)" }}
      >
        {String(val)}
      </span>
    ),
  },
  {
    key: "category" as const,
    header: "Category",
    render: (val: unknown) => {
      const cat = String(val);
      return <Badge color={categoryColorMap[cat] ?? "blue"}>{cat}</Badge>;
    },
  },
  {
    key: "description" as const,
    header: "Description",
    wrap: true,
  },
];

export default function Sbom() {
  const [activeFilter, setActiveFilter] = useState("All");
  const { contentRef } = usePageExport();

  const filtered =
    activeFilter === "All"
      ? sbomData
      : sbomData.filter((e) => e.category === activeFilter);

  return (
    <div
      ref={contentRef}
      className="page-content animate-fade-in-up"
      data-title="SBOM"
    >
      <PageHeader
        title="Software Bill of Materials"
        subtitle={`Full inventory of ${sbomData.length} packages and services used across the platform.`}
        pageTitle="SBOM"
        contentRef={contentRef}
      />

      <FilterPills
        options={filterOptions}
        active={activeFilter}
        onChange={setActiveFilter}
        className="mb-3"
      />

      <p className="text-sm mb-2" style={{ color: "var(--text-secondary)" }}>
        Showing {filtered.length} of {sbomData.length} entries
      </p>

      <DataTable<SbomEntry> columns={columns} data={filtered} />
    </div>
  );
}
