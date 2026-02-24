import { useState, useMemo } from 'react';
import { Download, FileText, FileType } from 'lucide-react';
import { SplitButton } from '@/components/ui';
import { exporterRegistry, downloadBlob, type Exporter, type EvalExportPayload } from '@/services/export';

interface ExportDropdownProps {
  /** Async function that resolves all eval data into the universal payload */
  getPayload: () => Promise<EvalExportPayload>;
  /** Title used for the downloaded filename */
  filenameBase: string;
  className?: string;
  size?: 'sm' | 'md';
  disabled?: boolean;
}

export function ExportDropdown({ getPayload, filenameBase, className, size = 'md', disabled = false }: ExportDropdownProps) {
  const [isExporting, setIsExporting] = useState<string | null>(null);

  const exporters = useMemo(() => exporterRegistry.getAll(), []);

  const getIconForExporter = (exporter: Exporter) => {
    switch (exporter.id) {
      case 'csv':
        return <FileText className="h-4 w-4" />;
      case 'pdf':
        return <FileType className="h-4 w-4" />;
      default:
        return <Download className="h-4 w-4" />;
    }
  };

  const handleExport = async (exporter: Exporter) => {
    setIsExporting(exporter.id);

    try {
      const payload = await getPayload();
      const blob = await exporter.export(payload);

      const safeTitle = filenameBase.replace(/[^a-z0-9]/gi, '_').toLowerCase();
      const filename = `${safeTitle}_${exporter.id}.${exporter.extension}`;

      downloadBlob(blob, filename);
    } catch (error) {
      console.error('Export failed:', error);
    } finally {
      setIsExporting(null);
    }
  };

  const primaryExporter = exporters[0];
  const dropdownExporters = exporters.slice(1);

  if (!primaryExporter) {
    return null;
  }

  return (
    <SplitButton
      className={className}
      primaryLabel="Export"
      primaryIcon={<Download className="h-4 w-4" />}
      primaryAction={() => handleExport(primaryExporter)}
      isLoading={isExporting === primaryExporter.id}
      disabled={disabled || isExporting !== null}
      variant="secondary"
      size={size}
      dropdownItems={dropdownExporters.map((exporter) => ({
        label: exporter.name,
        icon: getIconForExporter(exporter),
        action: () => handleExport(exporter),
        disabled: disabled || isExporting !== null,
      }))}
    />
  );
}
