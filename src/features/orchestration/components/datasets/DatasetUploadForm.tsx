import { useCallback, useMemo, useState } from 'react';
import { ArrowRight, X } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { FileDropZone } from '@/components/ui/FileDropZone';
import { Select } from '@/components/ui/Select';
import { cn } from '@/utils/cn';
import { CsvDataPreview } from '@/features/csvImport/components/CsvDataPreview';
import { CsvFileInfoBar } from '@/features/csvImport/components/CsvFileInfoBar';
import { useCsvImportWorkflow } from '@/features/csvImport/useCsvImportWorkflow';
import { analyzeDatasetHeaders } from '@/features/csvImport/utils';
import { useDatasetFormats } from '@/features/orchestration/queries/datasets';
import { ApiError } from '@/services/api/client';
import {
  orchestrationDatasetsApi,
  type DatasetVersionResponse,
} from '@/services/api/orchestrationDatasets';
import { notificationService } from '@/services/notifications';

type IdStrategy = 'column' | 'uuid';
type Step = 'upload' | 'configure';

interface Props {
  datasetId: string;
  onClose(): void;
  onUploaded(version: DatasetVersionResponse): void;
}

export function DatasetUploadForm({ datasetId, onClose, onUploaded }: Props) {
  const { data: formats = [], isLoading: formatsLoading } = useDatasetFormats();

  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>('upload');
  const [idStrategy, setIdStrategy] = useState<IdStrategy>('column');
  const [idColumn, setIdColumn] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const acceptExtensions = useMemo(
    () => formats.flatMap((f) => f.extensions),
    [formats],
  );
  const acceptAttr = useMemo(() => {
    const exts = formats.flatMap((f) => f.extensions);
    const mimes = formats.flatMap((f) => f.mimeTypes);
    return [...exts, ...mimes].join(',');
  }, [formats]);
  const allowedExtLabel = useMemo(
    () => acceptExtensions.join(', '),
    [acceptExtensions],
  );
  const formatsReady = !formatsLoading && acceptExtensions.length > 0;

  const { error, csvPreview, processFile, handleReset } = useCsvImportWorkflow<never>({
    file,
    data: null,
    columnMapping: new Map(),
    onFileChange: setFile,
    onDataChange: () => {},
    onColumnMappingChange: () => {},
    acceptExtensions,
  });

  const headerAnalysis = useMemo(
    () => (csvPreview ? analyzeDatasetHeaders(csvPreview.headers) : null),
    [csvPreview],
  );

  const previewError = useMemo(() => {
    if (!headerAnalysis) return null;
    if (headerAnalysis.columns.length === 0) {
      return 'Could not detect a header row. The file may be empty.';
    }
    if (headerAnalysis.interiorBlankPositions.length > 0) {
      const positions = headerAnalysis.interiorBlankPositions.join(', ');
      return `Blank column header at position ${positions}. Remove empty columns between named ones, then re-upload.`;
    }
    if (headerAnalysis.duplicates.length > 0) {
      return `Duplicate column header: ${headerAnalysis.duplicates.join(', ')}. Column names must be unique.`;
    }
    return null;
  }, [headerAnalysis]);

  const columnOptions = useMemo(() => {
    if (!headerAnalysis) return [];
    return headerAnalysis.columns
      .filter((name) => name.length > 0)
      .map((name) => ({ value: name, label: name }));
  }, [headerAnalysis]);

  const previewClean = Boolean(csvPreview && headerAnalysis && !previewError);

  const handleFilesSelected = useCallback(
    (files: File[]) => {
      const picked = files[0];
      if (!picked) return;
      setServerError(null);
      void processFile(picked);
    },
    [processFile],
  );

  const handleChangeFile = useCallback(() => {
    handleReset();
    setServerError(null);
    setIdColumn('');
  }, [handleReset]);

  const canSubmit = useMemo(() => {
    if (!file || !previewClean || submitting) return false;
    if (idStrategy === 'uuid') return true;
    return Boolean(idColumn);
  }, [file, previewClean, submitting, idStrategy, idColumn]);

  async function handleSubmit() {
    if (!file) return;
    setSubmitting(true);
    setServerError(null);
    try {
      const version = await orchestrationDatasetsApi.uploadVersion(
        datasetId,
        file,
        idStrategy,
        idStrategy === 'column' ? idColumn : undefined,
      );
      notificationService.success(
        `Imported ${version.rowCount} rows (v${version.versionNumber}).`,
      );
      onUploaded(version);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Upload failed';
      setServerError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-[var(--border-default)] px-5 py-4">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            Upload new version
          </h2>
          <p className="text-xs text-[var(--text-muted)]">
            {step === 'upload'
              ? 'Step 1 of 2 · Upload & preview'
              : 'Step 2 of 2 · Configure recipients'}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          disabled={submitting}
          className="rounded-md p-1 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex flex-1 flex-col overflow-y-auto px-5 py-4">
        {step === 'upload' ? (
          <div
            className={cn(
              'flex flex-1 flex-col gap-4',
              !file && 'items-center justify-center',
            )}
          >
            {!file ? (
              <div className="w-full max-w-lg">
                {formatsReady ? (
                  <FileDropZone
                    onFilesSelected={handleFilesSelected}
                    accept={acceptAttr}
                    inputAriaLabel="Data file"
                    acceptLabel={`Supported: ${allowedExtLabel}`}
                  />
                ) : (
                  <div className="flex h-40 items-center justify-center rounded-lg border-2 border-dashed border-[var(--border-default)] bg-[var(--bg-secondary)] text-xs text-[var(--text-muted)]">
                    Loading supported formats…
                  </div>
                )}
                {error ? (
                  <p className="mt-4 text-xs text-[var(--color-error)]">{error}</p>
                ) : null}
                {previewError ? (
                  <div
                    role="alert"
                    className="mt-4 rounded-[var(--radius-default)] border border-[var(--color-error)] bg-[var(--surface-error)] px-3 py-2 text-xs text-[var(--color-error)]"
                  >
                    {previewError}
                  </div>
                ) : null}
              </div>
            ) : (
              <>
                <CsvFileInfoBar
                  file={file}
                  variant={previewError ? 'error' : previewClean ? 'success' : 'neutral'}
                  onReset={handleChangeFile}
                />

                {error ? (
                  <p className="text-xs text-[var(--color-error)]">{error}</p>
                ) : null}

                {previewError ? (
                  <div
                    role="alert"
                    className="rounded-[var(--radius-default)] border border-[var(--color-error)] bg-[var(--surface-error)] px-3 py-2 text-xs text-[var(--color-error)]"
                  >
                    {previewError}
                  </div>
                ) : null}

                {csvPreview && previewClean ? (
                  <CsvDataPreview preview={csvPreview} />
                ) : null}
              </>
            )}
          </div>
        ) : (
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium text-[var(--text-primary)]">
              Recipient ID strategy
            </legend>
            <label className="flex items-start gap-2 text-sm text-[var(--text-primary)]">
              <input
                type="radio"
                name="id-strategy"
                value="column"
                checked={idStrategy === 'column'}
                onChange={() => setIdStrategy('column')}
                className="mt-1"
              />
              <span className="flex flex-col">
                <span>Use a column from the file</span>
                <span className="text-xs text-[var(--text-secondary)]">
                  Pick a column whose values are unique per row (e.g. phone number, lead id).
                </span>
              </span>
            </label>

            {idStrategy === 'column' ? (
              <div
                className={cn(
                  'ml-6 flex items-center gap-2 px-3 py-2 rounded-md border transition-colors',
                  idColumn
                    ? 'border-[var(--border-success)] bg-[var(--surface-success)]'
                    : 'border-[var(--border-default)] bg-[var(--bg-secondary)]/50',
                )}
              >
                <div className="flex-1 min-w-0">
                  <code className="font-mono text-[11px] px-1 py-px rounded bg-[var(--color-info-light)] text-[var(--color-info)]">
                    Recipient ID
                  </code>
                </div>
                <ArrowRight className="h-3 w-3 text-[var(--text-tertiary)] shrink-0" />
                <Select
                  value={idColumn}
                  onChange={(next) => setIdColumn(next)}
                  options={columnOptions}
                  placeholder="Select a column"
                  disabled={columnOptions.length === 0}
                  className={cn(
                    'w-44 shrink-0',
                    idColumn ? 'border-[var(--border-success)]' : undefined,
                  )}
                  size="sm"
                />
              </div>
            ) : null}

            <label className="flex items-start gap-2 text-sm text-[var(--text-primary)]">
              <input
                type="radio"
                name="id-strategy"
                value="uuid"
                checked={idStrategy === 'uuid'}
                onChange={() => setIdStrategy('uuid')}
                className="mt-1"
              />
              <span className="flex flex-col">
                <span>Auto-generate IDs (UUID per row)</span>
                <span className="text-xs text-[var(--text-secondary)]">
                  The server will assign a fresh UUID to every row.
                </span>
              </span>
            </label>

            {serverError ? (
              <div
                role="alert"
                className="mt-2 rounded-[var(--radius-default)] border border-[var(--color-error)] bg-[var(--surface-error)] px-3 py-2 text-xs text-[var(--color-error)]"
              >
                {serverError}
              </div>
            ) : null}
          </fieldset>
        )}
      </div>

      <div className="flex justify-end gap-2 border-t border-[var(--border-default)] px-5 py-3">
        {step === 'upload' ? (
          <>
            <Button variant="secondary" size="md" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button
              size="md"
              onClick={() => setStep('configure')}
              disabled={!previewClean}
            >
              Next
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="secondary"
              size="md"
              onClick={() => setStep('upload')}
              disabled={submitting}
            >
              Back
            </Button>
            <Button size="md" onClick={handleSubmit} disabled={!canSubmit} isLoading={submitting}>
              Upload version
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
