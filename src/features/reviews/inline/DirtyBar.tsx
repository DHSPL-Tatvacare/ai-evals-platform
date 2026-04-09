import { useState } from 'react';
import { Button, ConfirmDialog } from '@/components/ui';
import { Save, SendHorizontal, Trash2 } from 'lucide-react';

interface DirtyBarProps {
  changeCount: number;
  changeSummary?: string;
  saving?: boolean;
  onDiscard: () => void;
  onSaveDraft: () => void;
  onFinalize: () => void;
}

export function DirtyBar({ changeCount, changeSummary, saving = false, onDiscard, onSaveDraft, onFinalize }: DirtyBarProps) {
  const [discardOpen, setDiscardOpen] = useState(false);

  if (changeCount === 0) return null;

  return (
    <>
      <div className="sticky bottom-0 z-[var(--z-sticky)] -mx-1 border border-[var(--interactive-primary)]/25 bg-[color-mix(in_srgb,var(--interactive-primary)_9%,var(--bg-primary))] px-4 py-3 shadow-[0_-10px_24px_color-mix(in_srgb,var(--interactive-primary)_10%,transparent)] backdrop-blur-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[12px] font-semibold text-[var(--text-brand)]">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--text-brand)] animate-pulse" />
              {changeCount} unsaved {changeCount === 1 ? 'change' : 'changes'}
            </div>
            {changeSummary && (
              <p className="mt-1 truncate text-[11px] text-[var(--text-secondary)]">
                {changeSummary}
              </p>
            )}
          </div>
          <div className="flex gap-1.5 self-end md:self-auto">
            <Button variant="ghost" size="sm" icon={Trash2} onClick={() => setDiscardOpen(true)} disabled={saving}>
              Discard
            </Button>
            <Button variant="secondary" size="sm" icon={Save} onClick={onSaveDraft} isLoading={saving}>
              Save Draft
            </Button>
            <Button size="sm" icon={SendHorizontal} onClick={onFinalize} isLoading={saving}>
              Finalize
            </Button>
          </div>
        </div>
      </div>
      <ConfirmDialog
        isOpen={discardOpen}
        onClose={() => setDiscardOpen(false)}
        onConfirm={() => {
          setDiscardOpen(false);
          onDiscard();
        }}
        title="Discard review draft changes"
        description="Discard the current unsaved review changes? This cannot be undone."
        confirmLabel="Discard"
        variant="danger"
      />
    </>
  );
}
