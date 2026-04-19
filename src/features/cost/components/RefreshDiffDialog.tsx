import { Modal, Button } from '@/components/ui';
import type { RefreshDiff } from '../types';

interface RefreshDiffDialogProps {
  diff: RefreshDiff;
  onClose: () => void;
}

export function RefreshDiffDialog({ diff, onClose }: RefreshDiffDialogProps) {
  return (
    <Modal isOpen onClose={onClose} title="models.dev refresh">
      <div className="space-y-3 text-[13px]">
        {diff.deduped ? (
          <p className="text-[var(--text-secondary)]">
            The payload hash matches the last snapshot — no pricing rows were changed. A snapshot
            row was still recorded for audit.
          </p>
        ) : (
          <dl className="grid grid-cols-2 gap-y-2">
            <dt className="text-[var(--text-muted)]">Added</dt>
            <dd className="text-right tabular-nums font-semibold text-[var(--color-success)]">+{diff.addedCount}</dd>
            <dt className="text-[var(--text-muted)]">Updated</dt>
            <dd className="text-right tabular-nums font-semibold text-[var(--color-info)]">~{diff.updatedCount}</dd>
            <dt className="text-[var(--text-muted)]">Unchanged</dt>
            <dd className="text-right tabular-nums text-[var(--text-secondary)]">{diff.unchangedCount}</dd>
            <dt className="text-[var(--text-muted)]">Removed</dt>
            <dd className="text-right tabular-nums font-semibold text-[var(--color-warning)]">-{diff.removedCount}</dd>
            <dt className="text-[var(--text-muted)]">Model count</dt>
            <dd className="text-right tabular-nums text-[var(--text-secondary)]">{diff.modelCount}</dd>
          </dl>
        )}

        <p className="truncate font-mono text-[11px] text-[var(--text-muted)]">
          snapshot {diff.snapshotId.slice(0, 8)} · hash {diff.payloadHash.slice(0, 12)}
        </p>

        <div className="flex justify-end pt-2">
          <Button variant="primary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
  );
}
