export type { Exporter, EvalExportPayload, EvalExportEntry, ExportSource, ExportField, ExportHumanReview } from './types';
export { exporterRegistry } from './exporterRegistry';
export { csvExporter, pdfExporter } from './exporters';
export { resolveVoiceRxExport } from './resolvers';

// Initialize exporters on import
import { exporterRegistry } from './exporterRegistry';
import { csvExporter, pdfExporter } from './exporters';

exporterRegistry.register(csvExporter);
exporterRegistry.register(pdfExporter);

// Helper function to download a blob
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
