import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ApiError } from '@/services/api/client';
import {
  createDraftVersion,
  fireManualRun,
  getWorkflow,
  publishVersion,
} from '@/services/api/orchestration';
import type { WorkflowRun } from '@/features/orchestration/types';
import { notificationService } from '@/services/notifications';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import { useOrchestrationRoutes } from '@/features/orchestration/hooks/useOrchestrationRoutes';

function describeError(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return fallback;
}

interface WorkflowHeaderBarProps {
  onRunStarted?: (run: WorkflowRun) => void;
}

export function WorkflowHeaderBar({ onRunStarted }: WorkflowHeaderBarProps) {
  const navigate = useNavigate();
  const orchestrationRoutes = useOrchestrationRoutes();
  const workflowId = useWorkflowBuilderStore((s) => s.workflowId);
  const versionId = useWorkflowBuilderStore((s) => s.versionId);
  const name = useWorkflowBuilderStore((s) => s.workflowName);
  const dirty = useWorkflowBuilderStore((s) => s.dirty);
  const workflowType = useWorkflowBuilderStore((s) => s.workflowType);
  const currentPublishedVersionId = useWorkflowBuilderStore(
    (s) => s.currentPublishedVersionId,
  );

  const [busy, setBusy] = useState(false);
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);

  const handleBack = () => {
    if (dirty) {
      setShowLeaveConfirm(true);
      return;
    }
    navigate(orchestrationRoutes.campaigns);
  };

  const saveDraft = async (): Promise<string | null> => {
    if (!workflowId || !workflowType) return null;
    const store = useWorkflowBuilderStore.getState();
    const v = await createDraftVersion(workflowId, store.toDefinition());
    store.setMetadata({ workflowId, versionId: v.id, name, workflowType });
    store.hydrate(v.definition);
    return v.id;
  };

  const refreshPublishState = async () => {
    if (!workflowId) return;
    try {
      const wf = await getWorkflow(workflowId);
      useWorkflowBuilderStore
        .getState()
        .setCurrentPublishedVersionId(wf.currentPublishedVersionId);
    } catch {
      // Non-fatal — header state is best-effort. Real failures still surface
      // via Save / Publish toasts elsewhere.
    }
  };

  const handleSave = async () => {
    if (!workflowId || !workflowType) return;
    setBusy(true);
    try {
      await saveDraft();
      notificationService.success('Draft saved');
    } catch (e) {
      notificationService.error(describeError(e, 'Save failed'));
    } finally {
      setBusy(false);
    }
  };

  const handlePublish = async () => {
    if (!workflowId) return;
    setBusy(true);
    try {
      let target = versionId;
      if (!target || dirty) {
        target = await saveDraft();
      }
      if (!target) {
        notificationService.error('No draft version to publish');
        return;
      }
      await publishVersion(workflowId, target);
      // Refresh publish state so Run Now becomes enabled and the header
      // status pill flips from Draft → Published. Without this the user
      // has to reload to see the change.
      await refreshPublishState();
      notificationService.success('Published');
    } catch (e) {
      notificationService.error(describeError(e, 'Publish failed'));
    } finally {
      setBusy(false);
    }
  };

  const handleRun = async () => {
    if (!workflowId) return;
    setBusy(true);
    try {
      const run = await fireManualRun(workflowId);
      notificationService.success(`Run started: ${run.id.slice(0, 8)}`);
      onRunStarted?.(run);
    } catch (e) {
      notificationService.error(describeError(e, 'Run failed'));
    } finally {
      setBusy(false);
    }
  };

  const isPublished = Boolean(currentPublishedVersionId);
  // Disable Run Now until the workflow has a published version. Backend will
  // reject otherwise with `workflow has no published version`; failing in the
  // UI gives a clearer affordance.
  const runDisabled = busy || !isPublished;

  return (
    <>
    <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-2">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleBack}
          className="flex h-7 shrink-0 items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 text-[12px] font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-default)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
          aria-label="Back to campaigns"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Campaigns</span>
        </button>
        <span className="font-medium text-[var(--text-primary)]">
          {name || 'Untitled Workflow'}
        </span>
        <PublishStatusPill isPublished={isPublished} dirty={dirty} />
      </div>
      <div className="flex gap-2">
        <Button variant="secondary" onClick={handleSave} disabled={busy || !dirty}>
          Save Draft
        </Button>
        <Button variant="primary" onClick={handlePublish} disabled={busy}>
          Publish
        </Button>
        <Button
          variant="secondary"
          onClick={handleRun}
          disabled={runDisabled}
          title={runDisabled && !isPublished ? 'Publish a version before running' : undefined}
        >
          Run Now
        </Button>
      </div>
    </div>
    <ConfirmDialog
      isOpen={showLeaveConfirm}
      onClose={() => setShowLeaveConfirm(false)}
      onConfirm={() => {
        setShowLeaveConfirm(false);
        navigate(orchestrationRoutes.campaigns);
      }}
      title="Discard unsaved edits?"
      description="You have unsaved changes to this workflow. Leaving the builder will lose them — save the draft first if you want to keep them."
      confirmLabel="Leave"
      cancelLabel="Stay"
      variant="warning"
    />
    </>
  );
}

function PublishStatusPill({
  isPublished,
  dirty,
}: {
  isPublished: boolean;
  dirty: boolean;
}) {
  let label: string;
  let bg: string;
  let fg: string;
  if (!isPublished) {
    label = dirty ? 'Draft (unsaved)' : 'Draft';
    bg = 'var(--surface-warning)';
    fg = 'var(--color-warning)';
  } else if (dirty) {
    label = 'Published · unsaved edits';
    bg = 'var(--surface-warning)';
    fg = 'var(--color-warning)';
  } else {
    label = 'Published';
    bg = 'var(--surface-brand-subtle)';
    fg = 'var(--color-success)';
  }
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[11px] font-medium"
      style={{ backgroundColor: bg, color: fg }}
    >
      {label}
    </span>
  );
}
