import { GitFork, History, Lock, Share2 } from 'lucide-react';
import { Button } from '@/components/ui';

interface VersionLibraryActionsProps {
  canEdit: boolean;
  canShare: boolean;
  canFork: boolean;
  canShowHistory: boolean;
  historyOpen: boolean;
  onEdit?: () => void;
  onToggleVisibility?: () => void;
  onFork?: () => void;
  onToggleHistory?: () => void;
  shareLabel?: string;
}

export function VersionLibraryActions({
  canEdit,
  canShare,
  canFork,
  canShowHistory,
  historyOpen,
  onEdit,
  onToggleVisibility,
  onFork,
  onToggleHistory,
  shareLabel,
}: VersionLibraryActionsProps) {
  return (
    <div className="flex items-center gap-1">
      {canEdit && onEdit ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={onEdit}
          className="h-7 px-2 text-[11px]"
        >
          Edit
        </Button>
      ) : null}
      {canShare && onToggleVisibility ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleVisibility}
          className="h-7 px-2 text-[11px]"
          icon={shareLabel === 'Make private' ? Lock : Share2}
        >
          {shareLabel}
        </Button>
      ) : null}
      {canFork && onFork ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={onFork}
          className="h-7 px-2 text-[11px]"
          icon={GitFork}
        >
          Fork
        </Button>
      ) : null}
      {canShowHistory && onToggleHistory ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleHistory}
          className="h-7 px-2 text-[11px]"
          icon={History}
        >
          {historyOpen ? 'Hide history' : 'History'}
        </Button>
      ) : null}
    </div>
  );
}
