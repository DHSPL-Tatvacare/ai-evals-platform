/**
 * Compact action overflow menu for listing page header.
 * Consolidates data-source, export, and eval-variant actions
 * into a single MoreHorizontal dropdown so metrics stay prominent.
 */
import { useState, useRef, useEffect, useMemo, type ReactNode } from 'react';
import { MoreHorizontal, RefreshCw, Cloud, FileText, Download, FileJson, FileType, Play, Clock } from 'lucide-react';
import { Tooltip } from '@/components/ui';
import { exporterRegistry, downloadBlob, type Exporter } from '@/services/export';
import { cn } from '@/utils';
import type { Listing, AIEvaluation, HumanReview } from '@/types';

interface ActionItem {
  id: string;
  label: string;
  icon: ReactNode;
  action: () => void;
  disabled?: boolean;
  description?: string;
  /** Visual separator before this item */
  divider?: boolean;
}

interface ListingActionMenuProps {
  listing: Listing;
  aiEval: AIEvaluation | null;
  humanReview: HumanReview | null;
  /** Data-source actions */
  onFetchFromApi: () => void;
  onRefetchFromApi: () => void;
  onAddTranscript: () => void;
  /** Eval actions */
  onOpenEvalModal: (variant?: 'segments' | 'regular') => void;
  /** Operation flags */
  isFetching: boolean;
  isAddingTranscript: boolean;
  isAnyOperationInProgress: boolean;
  isEvaluating: boolean;
  canEvaluate: boolean;
}

export function ListingActionMenu({
  listing,
  aiEval,
  humanReview,
  onFetchFromApi,
  onRefetchFromApi,
  onAddTranscript,
  onOpenEvalModal,
  isFetching,
  isAddingTranscript,
  isAnyOperationInProgress,
  isEvaluating,
  canEvaluate,
}: ListingActionMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExporting, setIsExporting] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const hasExistingEval = !!aiEval;
  const hasApiResponse = !!listing.apiResponse;
  const hasTranscript = !!listing.transcript;

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [isOpen]);

  // Close on escape
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen]);

  // Build export actions from registry
  const exporters = useMemo(() => exporterRegistry.getAll(), []);

  const getExportIcon = (exporter: Exporter) => {
    switch (exporter.id) {
      case 'json':
      case 'corrections-json':
        return <FileJson className="h-3.5 w-3.5" />;
      case 'csv':
        return <FileText className="h-3.5 w-3.5" />;
      case 'pdf':
        return <FileType className="h-3.5 w-3.5" />;
      default:
        return <Download className="h-3.5 w-3.5" />;
    }
  };

  const handleExport = async (exporter: Exporter) => {
    setIsOpen(false);
    setIsExporting(exporter.id);
    try {
      const blob = await exporter.export({
        listing,
        exportedAt: new Date(),
        aiEval,
        humanReview,
      });
      const safeTitle = listing.title.replace(/[^a-z0-9]/gi, '_').toLowerCase();
      downloadBlob(blob, `${safeTitle}_${exporter.id}.${exporter.extension}`);
    } catch (error) {
      console.error('Export failed:', error);
    } finally {
      setIsExporting(null);
    }
  };

  // --- Build context-aware action list ---
  const actions: ActionItem[] = [];

  // Data source actions (vary by flow)
  if (listing.sourceType === 'pending') {
    actions.push({
      id: 'fetch-api',
      label: 'Fetch from API',
      icon: <Cloud className="h-3.5 w-3.5" />,
      action: () => { setIsOpen(false); onFetchFromApi(); },
      disabled: isAnyOperationInProgress,
    });
    actions.push({
      id: 'add-transcript',
      label: 'Add Transcripts',
      icon: <FileText className="h-3.5 w-3.5" />,
      action: () => { setIsOpen(false); onAddTranscript(); },
      disabled: isAnyOperationInProgress,
      description: 'Upload .txt or .json transcript file',
    });
  } else if (listing.sourceType === 'api') {
    actions.push({
      id: hasApiResponse ? 'refetch-api' : 'fetch-api',
      label: hasApiResponse ? 'Re-fetch from API' : 'Fetch from API',
      icon: hasApiResponse ? <RefreshCw className="h-3.5 w-3.5" /> : <Cloud className="h-3.5 w-3.5" />,
      action: () => { setIsOpen(false); if (hasApiResponse) { onRefetchFromApi(); } else { onFetchFromApi(); } },
      disabled: isAnyOperationInProgress || isFetching,
    });
  } else if (listing.sourceType === 'upload') {
    actions.push({
      id: 'update-transcript',
      label: hasTranscript ? 'Update Transcript' : 'Add Transcript',
      icon: <FileText className="h-3.5 w-3.5" />,
      action: () => { setIsOpen(false); onAddTranscript(); },
      disabled: isAnyOperationInProgress || isAddingTranscript,
    });
  }

  // Evaluation action — single entry point; variant selection happens in the modal
  if (isEvaluating) {
    actions.push({
      id: 'eval-running',
      label: 'Evaluation running...',
      icon: <Clock className="h-3.5 w-3.5 animate-pulse" />,
      action: () => setIsOpen(false),
      disabled: true,
      divider: true,
    });
  } else if (canEvaluate) {
    actions.push({
      id: 'run-eval',
      label: hasExistingEval ? 'Re-run Evaluation' : 'Run Evaluation',
      icon: hasExistingEval ? <RefreshCw className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />,
      action: () => { setIsOpen(false); onOpenEvalModal(); },
      disabled: isAnyOperationInProgress,
      divider: true,
    });
  }

  // Export actions
  if (exporters.length > 0) {
    exporters.forEach((exporter, i) => {
      actions.push({
        id: `export-${exporter.id}`,
        label: `Export ${exporter.name}`,
        icon: getExportIcon(exporter),
        action: () => handleExport(exporter),
        disabled: isAnyOperationInProgress || isExporting !== null,
        divider: i === 0,
      });
    });
  }

  return (
    <div className="flex items-center gap-1">
      {/* Single action menu — all actions consolidated */}
      <div ref={menuRef} className="relative">
        <Tooltip content="More actions" position="bottom">
          <button
            ref={buttonRef}
            type="button"
            onClick={() => setIsOpen(prev => !prev)}
            className={cn(
              'h-7 w-7 flex items-center justify-center rounded-md border transition-colors',
              isOpen
                ? 'bg-[var(--bg-tertiary)] border-[var(--border-default)] text-[var(--text-primary)]'
                : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--interactive-secondary)]',
            )}
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </Tooltip>

        {isOpen && (
          <div className="absolute right-0 top-full mt-1 z-50 min-w-[200px] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] shadow-lg py-1">
            {actions.map((item) => (
              <div key={item.id}>
                {item.divider && (
                  <div className="border-t border-[var(--border-subtle)] my-1" />
                )}
                <button
                  type="button"
                  onClick={item.action}
                  disabled={item.disabled}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-1.5 text-[12px] text-left transition-colors',
                    item.disabled
                      ? 'text-[var(--text-muted)] cursor-not-allowed opacity-50'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]',
                  )}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
