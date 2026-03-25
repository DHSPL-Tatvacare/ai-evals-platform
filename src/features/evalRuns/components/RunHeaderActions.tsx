/**
 * RunHeaderActions — shared Logs / Cancel / Delete button group for run detail pages.
 * Used by RunDetail (Kaira) and InsideSalesRunDetail.
 */

import { Link } from 'react-router-dom';
import { FileText, Ban, Trash2 } from 'lucide-react';
import { PermissionGate } from '@/components/auth/PermissionGate';

const actionBtnBase =
  'inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]';

interface RunHeaderActionsProps {
  logsHref: string;
  isActive: boolean;
  cancelling: boolean;
  deleting: boolean;
  onCancel: () => void;
  onDelete: () => void;
}

export function RunHeaderActions({
  logsHref,
  isActive,
  cancelling,
  deleting,
  onCancel,
  onDelete,
}: RunHeaderActionsProps) {
  return (
    <div className="ml-auto flex items-center gap-1.5 shrink-0">
      <Link
        to={logsHref}
        className={`${actionBtnBase} text-[var(--text-secondary)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] hover:bg-[var(--bg-tertiary)]`}
      >
        <FileText className="h-3 w-3" />
        Logs
      </Link>

      {isActive && (
        <PermissionGate action="eval:delete">
          <button
            onClick={onCancel}
            disabled={cancelling}
            className={`${actionBtnBase} text-[var(--color-warning)] bg-[var(--surface-warning)] border border-[var(--border-warning)] hover:opacity-80`}
          >
            <Ban className="h-3 w-3" />
            {cancelling ? 'Cancelling…' : 'Cancel'}
          </button>
        </PermissionGate>
      )}

      <PermissionGate action="eval:delete">
        <button
          onClick={onDelete}
          disabled={deleting || isActive}
          title={isActive ? 'Cannot delete a running evaluation. Cancel it first.' : undefined}
          className={`${actionBtnBase} text-[var(--color-error)] bg-[var(--surface-error)] border border-[var(--border-error)] hover:opacity-80`}
        >
          <Trash2 className="h-3 w-3" />
          {deleting ? 'Deleting…' : 'Delete'}
        </button>
      </PermissionGate>
    </div>
  );
}
