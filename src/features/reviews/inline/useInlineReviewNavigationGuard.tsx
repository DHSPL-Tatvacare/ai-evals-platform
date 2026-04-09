import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UnsavedChangesModal } from '@/components/feedback';
import { useInlineReviewOptional } from './InlineReviewProvider';

type PendingAction = (() => void) | null;

interface UseInlineReviewNavigationGuardOptions {
  captureLinks?: boolean;
}

export function useInlineReviewNavigationGuard({
  captureLinks = false,
}: UseInlineReviewNavigationGuardOptions = {}) {
  const navigate = useNavigate();
  const review = useInlineReviewOptional();
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);

  const needsGuard = !!review?.isEditing && !!review?.hasDirtyChanges && !review?.saving;

  const closeModal = useCallback(() => {
    setPendingAction(null);
  }, []);

  const runOrQueue = useCallback((action: () => void) => {
    if (!needsGuard) {
      action();
      return true;
    }

    setPendingAction(() => action);
    return false;
  }, [needsGuard]);

  useEffect(() => {
    if (!needsGuard) {
      setPendingAction(null);
    }
  }, [needsGuard]);

  useEffect(() => {
    if (!needsGuard || !captureLinks) return;

    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [needsGuard]);

  useEffect(() => {
    if (!needsGuard) return;

    const onDocumentClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }

      const target = event.target as HTMLElement | null;
      const anchor = target?.closest('a[href]') as HTMLAnchorElement | null;
      if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) {
        return;
      }

      const url = new URL(anchor.href, window.location.href);
      if (url.origin !== window.location.origin) {
        return;
      }

      const nextHref = `${url.pathname}${url.search}${url.hash}`;
      const currentHref = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      if (nextHref === currentHref) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      setPendingAction(() => () => navigate(nextHref));
    };

    document.addEventListener('click', onDocumentClick, true);
    return () => document.removeEventListener('click', onDocumentClick, true);
  }, [captureLinks, navigate, needsGuard]);

  const modal = useMemo(() => (
    <UnsavedChangesModal
      isOpen={pendingAction != null}
      onDiscard={async () => {
        await review?.discardDraft();
        const action = pendingAction;
        closeModal();
        action?.();
      }}
      onSave={async () => {
        await review?.saveDraft();
        const action = pendingAction;
        closeModal();
        action?.();
      }}
      onCancel={closeModal}
      isSaving={review?.saving}
    />
  ), [closeModal, pendingAction, review]);

  return {
    confirmNavigation: runOrQueue,
    guardModal: modal,
  };
}
