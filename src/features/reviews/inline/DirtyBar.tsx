import { useState } from 'react';
import { Button, ConfirmDialog } from '@/components/ui';
import { PencilLine, Save, SendHorizontal, Trash2 } from 'lucide-react';

interface DirtyBarProps {
  isEditing: boolean;
  changeCount: number;
  changeSummary?: string;
  saving?: boolean;
  onDiscard: () => void;
  onSaveDraft: () => void;
  onFinalize: () => void;
}

export function DirtyBar({ isEditing, changeCount, changeSummary, saving = false, onDiscard, onSaveDraft, onFinalize }: DirtyBarProps) {
  const [discardOpen, setDiscardOpen] = useState(false);

  if (!isEditing) return null;

  const hasDirty = changeCount > 0;

  return (
    <>
      <div className="sticky bottom-0 z-[var(--z-sticky)] -mx-1 border border-[var(--review-bar-border)] bg-[var(--review-bar-bg)] px-4 py-3 shadow-[0_-10px_24px_var(--review-bar-shadow)] backdrop-blur-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            {hasDirty ? (
              <>
                <div className="flex items-center gap-2 text-[12px] font-semibold text-[var(--text-brand)]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[var(--text-brand)] animate-pulse" />
                  {changeCount} unsaved {changeCount === 1 ? 'change' : 'changes'}
                </div>
                {changeSummary && (
                  <p className="mt-1 truncate text-[11px] text-[var(--text-secondary)]">
                    {changeSummary}
                  </p>
                )}
              </>
            ) : (
              <div className="flex items-center gap-2 text-[12px] font-medium text-[var(--text-secondary)]">
                <PencilLine className="h-3.5 w-3.5" />
                Review in progress
              </div>
            )}
          </div>
          <div className="flex gap-1.5 self-end md:self-auto">
            <Button variant="ghost" size="sm" icon={Trash2} onClick={() => setDiscardOpen(true)} disabled={saving}>
              Discard
            </Button>
            {hasDirty && (
              <Button variant="secondary" size="sm" icon={Save} onClick={onSaveDraft} isLoading={saving}>
                Save Draft
              </Button>
            )}
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
        title="Discard review draft"
        description={hasDirty
          ? 'Discard the current review draft and all unsaved changes? This cannot be undone.'
          : 'Discard the review draft? This cannot be undone.'}
        confirmLabel="Discard"
        variant="danger"
      />
    </>
  );
}
