import { useEffect, useMemo, useState } from 'react';
import { Check, MessageCircle, PenLine } from 'lucide-react';
import { Button, Modal, Popover, PopoverContent, PopoverTrigger, Select } from '@/components/ui';
import { cn } from '@/utils/cn';
import type { ReviewDecision } from '@/types';

interface InlineReviewControlsProps {
  decision: ReviewDecision | '' | null | undefined;
  note?: string | null;
  originalValue?: string | null;
  reviewedValue?: string | null;
  allowedValues?: string[];
  disabled?: boolean;
  onAccept: () => void;
  onOverride: (reviewedValue: string) => void;
  onNote: (note: string | null) => void;
}

function getInitialOverrideValue(
  allowedValues: string[],
  originalValue: string | null | undefined,
  reviewedValue: string | null | undefined,
): string {
  if (reviewedValue && allowedValues.includes(reviewedValue)) {
    return reviewedValue;
  }
  const nextValue = allowedValues.find((value) => value !== originalValue);
  return nextValue ?? allowedValues[0] ?? '';
}

export function InlineReviewControls({
  decision,
  note,
  originalValue,
  reviewedValue,
  allowedValues = [],
  disabled = false,
  onAccept,
  onOverride,
  onNote,
}: InlineReviewControlsProps) {
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [draftOverrideValue, setDraftOverrideValue] = useState(
    getInitialOverrideValue(allowedValues, originalValue, reviewedValue),
  );
  const [draftNote, setDraftNote] = useState(note ?? '');

  const isAccepted = decision === 'accept';
  const isOverridden = decision === 'reject' || decision === 'correct';
  const hasNote = !!note?.trim();
  const overrideOptions = useMemo(
    () => allowedValues.map((value) => ({ value, label: value })),
    [allowedValues],
  );

  useEffect(() => {
    setDraftOverrideValue(getInitialOverrideValue(allowedValues, originalValue, reviewedValue));
  }, [allowedValues, originalValue, reviewedValue]);

  useEffect(() => {
    setDraftNote(note ?? '');
  }, [note]);

  if (disabled) return null;

  return (
    <>
      <span className="inline-flex items-center gap-px rounded-md border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] p-px">
        <button
          type="button"
          onClick={onAccept}
          className={cn(
            'inline-flex h-5 w-[22px] items-center justify-center rounded transition-colors',
            isAccepted
              ? 'bg-[var(--surface-success)] text-[var(--color-success)]'
              : 'text-[var(--text-muted)] hover:bg-[var(--surface-success)] hover:text-[var(--color-success)]',
          )}
          title="Accept"
        >
          <Check className="h-3 w-3" />
        </button>
        <Popover open={overrideOpen} onOpenChange={setOverrideOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                'inline-flex h-5 w-[22px] items-center justify-center rounded transition-colors',
                isOverridden
                  ? 'bg-[var(--surface-warning)] text-[var(--color-warning)]'
                  : 'text-[var(--text-muted)] hover:bg-[var(--surface-warning)] hover:text-[var(--color-warning)]',
              )}
              title="Override"
            >
              <PenLine className="h-3 w-3" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-64 gap-3 p-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                Override verdict
              </p>
              {originalValue && (
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  AI value: <span className="font-semibold text-[var(--text-primary)]">{originalValue}</span>
                </p>
              )}
            </div>
            <Select
              value={draftOverrideValue}
              onChange={setDraftOverrideValue}
              options={overrideOptions}
              size="sm"
            />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setOverrideOpen(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  onOverride(draftOverrideValue);
                  setOverrideOpen(false);
                }}
                disabled={!draftOverrideValue || draftOverrideValue === originalValue}
              >
                Apply
              </Button>
            </div>
          </PopoverContent>
        </Popover>
        <button
          type="button"
          onClick={() => setNoteOpen(true)}
          className={cn(
            'inline-flex h-5 w-[22px] items-center justify-center rounded transition-colors',
            hasNote
              ? 'text-[var(--color-info)]'
              : 'text-[var(--text-muted)] hover:text-[var(--color-info)]',
          )}
          title="Note"
        >
          <MessageCircle className="h-3 w-3" />
        </button>
      </span>

      <Modal isOpen={noteOpen} onClose={() => setNoteOpen(false)} title="Review note" className="max-w-md">
        <div className="space-y-4">
          <textarea
            value={draftNote}
            onChange={(event) => setDraftNote(event.target.value)}
            rows={5}
            className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/30"
            placeholder="Add reviewer context"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setNoteOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                onNote(draftNote.trim() ? draftNote : null);
                setNoteOpen(false);
              }}
            >
              Save note
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
