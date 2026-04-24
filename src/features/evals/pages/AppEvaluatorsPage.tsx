import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, ConfirmDialog, FilterButton, PageHeaderSearch, PageSurface } from '@/components/ui';
import { evaluatorDetailForApp } from '@/config/routes';
import { useCurrentAppConfig, useCurrentAppId, useCurrentAppMetadata } from '@/hooks';
import { CreateEvaluatorWizard, EvaluatorsTable } from '@/features/evals/components';
import { filterEvaluatorsByVisibility } from '@/services/api/evaluatorsApi';
import { notificationService } from '@/services/notifications';
import { useEvaluatorsStore } from '@/stores';
import { useAuthStore } from '@/stores/authStore';
import { usePermission } from '@/utils/permissions';
import { evaluatorShowsInHeader, getEvaluatorMainMetricField, setEvaluatorHeaderVisibility } from '@/features/evals/utils/evaluatorMetadata';
import { usePageMetadata } from '@/config/pageMetadata';
import { useAppPageActions } from '@/features/pageActions/registry';
import type {
  EvaluatorDefinition,
  EvaluatorVisibilityFilter,
  EvaluatorContext,
} from '@/types';
import { RotateCcw } from 'lucide-react';

interface AppEvaluatorsPageProps {
  onOpenEvaluator?: (evaluator: EvaluatorDefinition) => void;
}

export function AppEvaluatorsPage({ onOpenEvaluator }: AppEvaluatorsPageProps = {}) {
  const navigate = useNavigate();
  const appId = useCurrentAppId();
  const appConfig = useCurrentAppConfig();
  const appMetadata = useCurrentAppMetadata();
  const { icon, title } = usePageMetadata('evaluators');
  const headerPageActions = useAppPageActions('evaluators', { displayMode: 'icon' });
  const emptyStatePageActions = useAppPageActions('evaluators');
  const canCreate = usePermission('asset:create');
  const canEdit = usePermission('asset:edit');
  const canDelete = usePermission('asset:delete');
  const canShare = usePermission('asset:share');
  const isOwner = useAuthStore((state) => state.user?.isOwner ?? false);
  const [filter, setFilter] = useState<EvaluatorVisibilityFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [editingEvaluator, setEditingEvaluator] = useState<EvaluatorDefinition | undefined>();
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [evaluatorToDelete, setEvaluatorToDelete] = useState<EvaluatorDefinition | undefined>();
  const [isSeeding, setIsSeeding] = useState(false);

  const {
    evaluators,
    isLoaded,
    currentAppId,
    currentListingId,
    loadAppEvaluators,
    addEvaluator,
    updateEvaluator,
    deleteEvaluator,
    setVisibility,
    forkEvaluator,
    seedAppDefaults,
  } = useEvaluatorsStore();

  const supportsAppLevelSeedDefaults =
    appConfig.features.hasAdversarial || appConfig.features.hasRubricMode;

  useEffect(() => {
    if (!isLoaded || currentAppId !== appId || currentListingId !== null) {
      loadAppEvaluators(appId);
    }
  }, [appId, currentAppId, currentListingId, isLoaded, loadAppEvaluators]);

  const filteredEvaluators = useMemo(
    () => filterEvaluatorsByVisibility(evaluators, filter),
    [evaluators, filter],
  );
  const context: EvaluatorContext = useMemo(() => ({ appId }), [appId]);

  const handleSave = async (evaluator: EvaluatorDefinition) => {
    if (editingEvaluator) {
      await updateEvaluator(evaluator);
      notificationService.success('Evaluator updated');
    } else {
      await addEvaluator(evaluator);
      notificationService.success('Evaluator created');
    }
    setEditingEvaluator(undefined);
  };

  const handleVisibilityChange = async (evaluator: EvaluatorDefinition) => {
    const nextVisibility = evaluator.visibility === 'shared' ? 'private' : 'shared';
    await setVisibility(evaluator.id, nextVisibility);
    notificationService.success(
      nextVisibility === 'shared' ? 'Evaluator shared' : 'Evaluator made private',
    );
  };

  const handleToggleHeader = async (evaluator: EvaluatorDefinition) => {
    if (!getEvaluatorMainMetricField(evaluator)) {
      notificationService.error('Select a main metric before changing header visibility');
      return;
    }

    const nextShowInHeader = !evaluatorShowsInHeader(evaluator);
    await updateEvaluator({
      ...evaluator,
      outputSchema: setEvaluatorHeaderVisibility(evaluator.outputSchema, nextShowInHeader),
      updatedAt: new Date(),
    });
    notificationService.success(
      nextShowInHeader ? 'Evaluator added to header' : 'Evaluator removed from header',
    );
  };

  const handleFork = async (evaluator: EvaluatorDefinition) => {
    const forked = await forkEvaluator(evaluator.id);
    notificationService.success(`Forked evaluator: ${forked.name}`);
  };

  const handleConfirmDelete = async () => {
    if (!evaluatorToDelete) {
      return;
    }

    await deleteEvaluator(evaluatorToDelete.id);
    notificationService.success('Evaluator deleted');
    setDeleteConfirmOpen(false);
    setEvaluatorToDelete(undefined);
  };

  const handleRestoreDefaults = async () => {
    if (!supportsAppLevelSeedDefaults) {
      return;
    }

    setIsSeeding(true);
    try {
      const seeded = await seedAppDefaults(appId);
      if (seeded.length > 0) {
        notificationService.success(`Restored ${seeded.length} missing default evaluators`);
      } else {
        notificationService.info('All default evaluators are already present');
      }
    } catch (error) {
      notificationService.error(
        error instanceof Error ? error.message : 'Failed to restore defaults',
      );
    } finally {
      setIsSeeding(false);
    }
  };

  const handleOpenCreate = () => {
    setEditingEvaluator(undefined);
    setIsWizardOpen(true);
  };

  const showRestore = supportsAppLevelSeedDefaults && isOwner;
  const defaultOpenEvaluator = useMemo(() => {
    if (onOpenEvaluator || !appConfig.navigation.evaluatorDetailPath) {
      return onOpenEvaluator;
    }

    return (evaluator: EvaluatorDefinition) => {
      const detailPath = evaluatorDetailForApp(appId, evaluator.id);
      if (detailPath) {
        navigate(detailPath);
      }
    };
  }, [appConfig.navigation.evaluatorDetailPath, appId, navigate, onOpenEvaluator]);

  const headerActions = (
    <>
      {headerPageActions}
      {showRestore && (
        <Button
          variant="secondary"
          size="sm"
          icon={RotateCcw}
          iconOnly
          onClick={handleRestoreDefaults}
          isLoading={isSeeding}
          aria-label="Restore defaults"
          title="Restore defaults"
        >
          Restore Defaults
        </Button>
      )}
      {canCreate && <Button onClick={handleOpenCreate}>Create Evaluator</Button>}
    </>
  );

  const headerFilters = (
    <>
      <PageHeaderSearch
        value={searchQuery}
        onChange={setSearchQuery}
        placeholder="Search evaluators…"
        label="Search evaluators"
      />
      <FilterButton
        activeCount={filter === 'all' ? 0 : 1}
        onClick={() => setFilterPanelOpen(true)}
        iconOnly
      />
    </>
  );

  return (
    <PageSurface icon={icon} title={title} filters={headerFilters} actions={headerActions}>
      <EvaluatorsTable
        evaluators={filteredEvaluators}
        loading={!isLoaded}
        filter={filter}
        onFilterChange={setFilter}
        onCreate={handleOpenCreate}
        onEdit={canEdit ? (evaluator) => {
          setEditingEvaluator(evaluator);
          setIsWizardOpen(true);
        } : undefined}
        onFork={canCreate ? handleFork : undefined}
        onDelete={canDelete ? (evaluator) => {
          setEvaluatorToDelete(evaluator);
          setDeleteConfirmOpen(true);
        } : undefined}
        onVisibilityChange={canShare ? handleVisibilityChange : undefined}
        onRestoreDefaults={showRestore ? handleRestoreDefaults : undefined}
        onToggleHeader={handleToggleHeader}
        isRestoringDefaults={isSeeding}
        title="Evaluators"
        description={`Manage private and shared evaluators for ${appMetadata.name}.`}
        emptyStateActions={emptyStatePageActions.length > 0 ? <>{emptyStatePageActions}</> : undefined}
        hideHeader
        searchQuery={searchQuery}
        filterPanelOpen={filterPanelOpen}
        onFilterPanelOpenChange={setFilterPanelOpen}
        onOpen={defaultOpenEvaluator}
        canCreate={canCreate}
        canEditOwned={canEdit}
        canDeleteOwned={canDelete}
        canShareOwned={canShare}
        canManageSeededDefaults={isOwner}
      />

      {isWizardOpen ? (
        <CreateEvaluatorWizard
          isOpen={isWizardOpen}
          onClose={() => {
            setIsWizardOpen(false);
            setEditingEvaluator(undefined);
          }}
          onSave={handleSave}
          context={context}
          editEvaluator={editingEvaluator}
        />
      ) : null}

      <ConfirmDialog
        isOpen={deleteConfirmOpen}
        onClose={() => {
          setDeleteConfirmOpen(false);
          setEvaluatorToDelete(undefined);
        }}
        onConfirm={handleConfirmDelete}
        title="Delete Evaluator"
        description="Are you sure you want to delete this evaluator? This action cannot be undone."
        confirmLabel="Delete"
        variant="danger"
      />
    </PageSurface>
  );
}
