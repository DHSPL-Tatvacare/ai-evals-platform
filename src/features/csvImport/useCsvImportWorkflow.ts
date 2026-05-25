import { useCallback, useMemo, useState } from 'react';

import type { ColumnMapping, CsvFieldDef, CsvPreviewResult, HeaderValidation } from './types';
import { parseCsvPreview, parseXlsxPreview, remapCsvContent, validateCsvHeaders } from './utils';

interface UseCsvImportWorkflowArgs<TData> {
  schema?: CsvFieldDef[];
  file: File | null;
  data: TData | null;
  columnMapping: ColumnMapping;
  onFileChange: (file: File | null) => void;
  onDataChange: (data: TData | null) => void;
  onColumnMappingChange: (mapping: ColumnMapping) => void;
  analyzeCsv?: (args: { file: File; csvText: string }) => Promise<TData>;
  previewRows?: number;
  maxFileSizeMb?: number;
  acceptExtensions?: string[];
}

export function useCsvImportWorkflow<TData>({
  schema,
  file,
  data,
  columnMapping,
  onFileChange,
  onDataChange,
  onColumnMappingChange,
  analyzeCsv,
  previewRows = 10,
  maxFileSizeMb = 50,
  acceptExtensions = ['.csv'],
}: UseCsvImportWorkflowArgs<TData>) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [csvPreview, setCsvPreview] = useState<CsvPreviewResult | null>(null);
  const [headerValidation, setHeaderValidation] = useState<HeaderValidation | null>(null);
  const [rawCsvText, setRawCsvText] = useState<string | null>(null);

  const needsMapping = Boolean(headerValidation && !headerValidation.isValid);
  const mappingComplete = useMemo(
    () => Boolean(needsMapping && headerValidation?.missing.every((field) => columnMapping.has(field))),
    [columnMapping, headerValidation, needsMapping],
  );

  const runAnalysis = useCallback(async (selectedFile: File, csvText: string) => {
    if (!analyzeCsv) {
      return;
    }
    setIsProcessing(true);
    setError(null);
    try {
      const analyzedData = await analyzeCsv({ file: selectedFile, csvText });
      onDataChange(analyzedData);
    } catch (err) {
      onDataChange(null);
      setError(err instanceof Error ? err.message : 'Failed to process CSV file.');
    } finally {
      setIsProcessing(false);
    }
  }, [analyzeCsv, onDataChange]);

  const processFile = useCallback(async (selectedFile: File) => {
    setError(null);
    setCsvPreview(null);
    setHeaderValidation(null);
    setRawCsvText(null);
    onColumnMappingChange(new Map());
    onDataChange(null);

    const lowerName = selectedFile.name.toLowerCase();
    const matchedExtension = acceptExtensions.find((ext) =>
      lowerName.endsWith(ext.toLowerCase()),
    );
    if (!matchedExtension) {
      const allowed = acceptExtensions.join(', ');
      setError(`Unsupported file type. Allowed: ${allowed}.`);
      return;
    }

    if (selectedFile.size > maxFileSizeMb * 1024 * 1024) {
      setError(`File size exceeds ${maxFileSizeMb}MB limit.`);
      return;
    }

    let text: string | null = null;
    let preview: CsvPreviewResult;
    if (matchedExtension.toLowerCase() === '.xlsx') {
      preview = await parseXlsxPreview(selectedFile, previewRows);
    } else {
      text = await selectedFile.text();
      preview = parseCsvPreview(text, previewRows);
    }

    const validation = schema
      ? validateCsvHeaders(preview.headers, schema)
      : { matched: preview.headers, missing: [], extra: [], isValid: true };

    setRawCsvText(text);
    setCsvPreview(preview);
    setHeaderValidation(validation);
    onFileChange(selectedFile);

    if (validation.isValid && analyzeCsv && text !== null) {
      await runAnalysis(selectedFile, text);
    }
  }, [acceptExtensions, analyzeCsv, maxFileSizeMb, onColumnMappingChange, onDataChange, onFileChange, previewRows, runAnalysis, schema]);

  const handleApplyMapping = useCallback(async () => {
    if (!rawCsvText || !file || !schema) {
      return;
    }

    const remappedText = remapCsvContent(rawCsvText, columnMapping);
    const preview = parseCsvPreview(remappedText, previewRows);
    const validation = validateCsvHeaders(preview.headers, schema);

    setRawCsvText(remappedText);
    setCsvPreview(preview);
    setHeaderValidation(validation);

    if (validation.isValid) {
      await runAnalysis(file, remappedText);
    }
  }, [columnMapping, file, previewRows, rawCsvText, runAnalysis, schema]);

  const handleRetry = useCallback(async () => {
    if (!file || !rawCsvText) {
      return;
    }
    await runAnalysis(file, rawCsvText);
  }, [file, rawCsvText, runAnalysis]);

  const handleReset = useCallback(() => {
    onFileChange(null);
    onDataChange(null);
    onColumnMappingChange(new Map());
    setError(null);
    setCsvPreview(null);
    setHeaderValidation(null);
    setRawCsvText(null);
  }, [onColumnMappingChange, onDataChange, onFileChange]);

  return {
    data,
    error,
    csvPreview,
    headerValidation,
    isProcessing,
    needsMapping,
    mappingComplete,
    processFile,
    handleApplyMapping,
    handleRetry,
    handleReset,
  };
}
