import { useCallback, useMemo, useRef, useState } from 'react';
import { RotateCcw, Upload } from 'lucide-react';

import { Alert } from '@/components/ui';
import { notificationService } from '@/services/notifications';
import { cn } from '@/utils';
import { CsvDataPreview } from '@/features/csvImport/components/CsvDataPreview';
import { CsvFieldCallout } from '@/features/csvImport/components/CsvFieldCallout';
import { CsvFieldMapper } from '@/features/csvImport/components/CsvFieldMapper';
import { CsvFileInfoBar } from '@/features/csvImport/components/CsvFileInfoBar';
import { useCsvImportWorkflow } from '@/features/csvImport/useCsvImportWorkflow';
import { parseCsvRecords } from '@/features/csvImport/utils';

import type { CredentialPoolConfig, CredentialPoolEntry } from './types';
import { createCredentialPoolEntry } from './utils';

interface CredentialCsvImportProps {
  config: CredentialPoolConfig;
  onImportEntries: (entries: CredentialPoolEntry[]) => void;
}

export function CredentialCsvImport({ config, onImportEntries }: CredentialCsvImportProps) {
  const [file, setFile] = useState<File | null>(null);
  const [records, setRecords] = useState<Record<string, string>[] | null>(null);
  const [columnMapping, setColumnMapping] = useState<Map<string, string>>(new Map());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const {
    csvPreview,
    error,
    headerValidation,
    isProcessing,
    needsMapping,
    mappingComplete,
    processFile,
    handleApplyMapping,
    handleRetry,
    handleReset,
  } = useCsvImportWorkflow<Record<string, string>[]>({
    schema: config.csvSchema,
    file,
    data: records,
    columnMapping,
    onFileChange: setFile,
    onDataChange: setRecords,
    onColumnMappingChange: setColumnMapping,
    analyzeCsv: async ({ csvText }) => parseCsvRecords(csvText),
  });

  const importableEntries = useMemo(
    () => (records ?? []).map((record) => createCredentialPoolEntry(record, 'csv')),
    [records],
  );

  const resetInput = useCallback(() => {
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  const handleResetWithInput = useCallback(() => {
    handleReset();
    resetInput();
  }, [handleReset, resetInput]);

  const commitImport = useCallback(() => {
    if (importableEntries.length === 0) {
      return;
    }
    onImportEntries(importableEntries);
    notificationService.success(`Imported ${importableEntries.length} credential row${importableEntries.length === 1 ? '' : 's'}.`);
    handleResetWithInput();
  }, [handleResetWithInput, importableEntries, onImportEntries]);

  return (
    <div className="space-y-3 rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
      <div>
        <h4 className="text-[13px] font-medium text-[var(--text-primary)]">Import from CSV</h4>
        <p className="text-[11px] text-[var(--text-muted)]">
          Upload a CSV, map the user/token columns if needed, then add the imported rows into the current pool.
        </p>
      </div>

      {!file && (
        <>
          <CsvFieldCallout schema={config.csvSchema} title="Credential CSV Format" />
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              setIsDragging(false);
            }}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragging(false);
              const droppedFile = e.dataTransfer.files[0];
              if (droppedFile) {
                void processFile(droppedFile);
              }
            }}
            className={cn(
              'relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed text-center transition-all py-8 px-6 cursor-pointer',
              isDragging
                ? 'border-[var(--border-brand)] bg-[var(--color-brand-accent)]/10'
                : 'border-[var(--border-default)] bg-[var(--bg-primary)]',
              'hover:border-[var(--border-brand)] hover:bg-[var(--color-brand-accent)]/5',
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={(e) => {
                const selectedFile = e.target.files?.[0];
                if (selectedFile) {
                  void processFile(selectedFile);
                }
              }}
              className="absolute inset-0 cursor-pointer opacity-0"
            />
            <div className="flex items-center justify-center rounded-full bg-[var(--color-brand-accent)]/20 mb-3 h-10 w-10">
              <Upload className="h-5 w-5 text-[var(--text-brand)]" />
            </div>
            <p className="text-[14px] font-medium text-[var(--text-primary)]">
              {isDragging ? 'Drop credential CSV here' : 'Drop CSV file or click to browse'}
            </p>
          </div>
          {error && <Alert variant="error">{error}</Alert>}
        </>
      )}

      {file && isProcessing && (
        <div className="space-y-3">
          <CsvFileInfoBar file={file} variant="neutral" onReset={handleResetWithInput} />
          <div className="flex items-center gap-3 px-4 py-3 rounded-[6px] bg-[var(--bg-primary)] border border-[var(--border-subtle)]">
            <div className="h-4 w-4 border-2 border-[var(--interactive-primary)] border-t-transparent rounded-full animate-spin" />
            <span className="text-[13px] text-[var(--text-secondary)]">Parsing credential CSV...</span>
          </div>
        </div>
      )}

      {file && error && !isProcessing && (
        <div className="space-y-3">
          <CsvFileInfoBar file={file} variant="error" onReset={handleResetWithInput} />
          <Alert variant="error">{error}</Alert>
          <button
            onClick={() => { void handleRetry(); }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)] bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-md hover:bg-[var(--bg-secondary)] transition-colors"
          >
            <RotateCcw className="h-3 w-3" />
            Retry
          </button>
        </div>
      )}

      {file && needsMapping && !isProcessing && !error && headerValidation && (
        <div className="space-y-3">
          <CsvFileInfoBar file={file} variant="warning" onReset={handleResetWithInput} />
          <CsvFieldMapper
            csvHeaders={csvPreview?.headers ?? []}
            schema={config.csvSchema}
            mapping={columnMapping}
            onMappingChange={setColumnMapping}
            missingFields={headerValidation.missing}
          />
          {mappingComplete && (
            <button
              onClick={() => { void handleApplyMapping(); }}
              className="w-full px-4 py-2 text-[13px] font-medium rounded-md bg-[var(--interactive-primary)] text-white hover:opacity-90 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]"
            >
              Apply Mapping & Parse
            </button>
          )}
          {csvPreview && <CsvDataPreview preview={csvPreview} schema={config.csvSchema} columnMapping={columnMapping} />}
        </div>
      )}

      {file && records && !isProcessing && !error && !needsMapping && (
        <div className="space-y-3">
          <CsvFileInfoBar file={file} variant="success" onReset={handleResetWithInput} />
          <div className="rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2">
            <p className="text-[12px] font-medium text-[var(--text-primary)]">
              Ready to import {importableEntries.length} credential row{importableEntries.length === 1 ? '' : 's'}.
            </p>
          </div>
          {csvPreview && <CsvDataPreview preview={csvPreview} schema={config.csvSchema} />}
          <button
            onClick={commitImport}
            className="w-full px-4 py-2 text-[13px] font-medium rounded-md bg-[var(--interactive-primary)] text-white hover:opacity-90 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]"
          >
            Add Imported Rows
          </button>
        </div>
      )}
    </div>
  );
}
