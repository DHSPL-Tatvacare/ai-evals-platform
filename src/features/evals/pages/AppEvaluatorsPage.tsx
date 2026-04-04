import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { ConfirmDialog, Skeleton } from '@/components/ui';
import { useCurrentAppConfig, useCurrentAppId, useCurrentAppMetadata } from '@/hooks';
import { CreateEvaluatorWizard, EvaluatorsTable } from '@/features/evals/components';
import { rulesRepository } from '@/services/api';
import { filterEvaluatorsByVisibility } from '@/services/api/evaluatorsApi';
import { notificationService } from '@/services/notifications';
import { useEvaluatorsStore } from '@/stores';
import { usePermission } from '@/utils/permissions';
import type {
  EvaluatorDefinition,
  EvaluatorVisibilityFilter,
  RuleCatalogEntry,
  EvaluatorContext,
} from '@/types';

interface AppEvaluatorsPageProps {
  extraHeaderActions?: ReactNode;
  extraEmptyStateActions?: ReactNode;
  onOpenEvaluator?: (evaluator: EvaluatorDefinition) => void;
}

export function AppEvaluatorsPage({
  extraHeaderActions,
  extraEmptyStateActions,
  onOpenEvaluator,
}: AppEvaluatorsPageProps) {
  const appId = useCurrentAppId();
  const appConfig = useCurrentAppConfig();
  const appMetadata = useCurrentAppMetadata();
  const canCreate = usePermission('resource:create');
  const [filter, setFilter] = useState<EvaluatorVisibilityFilter>('all');
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [editingEvaluator, setEditingEvaluator] = useState<EvaluatorDefinition | undefined>();
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [evaluatorToDelete, setEvaluatorToDelete] = useState<EvaluatorDefinition | undefined>();
  const [isSeeding, setIsSeeding] = useState(false);
  const [rules, setRules] = useState<RuleCatalogEntry[]>([]);

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

  useEffect(() => {
    if (!appConfig.features.hasRules) {
      setRules([]);
      return;
    }

    let cancelled = false;
    rulesRepository.get(appId)
      .then((response) => {
        if (!cancelled) {
          setRules(response.rules);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRules([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [appConfig.features.hasRules, appId]);

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
      nextVisibility === 'shared'
        ? 'Evaluator shared'
        : 'Evaluator moved to private library',
    );
  };

  const handleToggleHeader = async (evaluator: EvaluatorDefinition) => {
    await updateEvaluator({
      ...evaluator,
      showInHeader: !evaluator.showInHeader,
      updatedAt: new Date(),
    });
    notificationService.success(
      evaluator.showInHeader ? 'Evaluator removed from header' : 'Evaluator added to header',
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

  const handleSeedDefaults = async () => {
    if (!supportsAppLevelSeedDefaults) {
      return;
    }

    setIsSeeding(true);
    try {
      const seeded = await seedAppDefaults(appId);
      notificationService.success(`Added ${seeded.length} default evaluators`);
    } catch (error) {
      notificationService.error(
        error instanceof Error ? error.message : 'Failed to seed defaults',
      );
    } finally {
      setIsSeeding(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      {!isLoaded ? (
        <div className="grid grid-cols-1 gap-4 pt-6 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <EvaluatorsTable
          evaluators={filteredEvaluators}
          rules={rules}
          filter={filter}
          onFilterChange={setFilter}
          onCreate={() => {
            setEditingEvaluator(undefined);
            setIsWizardOpen(true);
          }}
          onEdit={(evaluator) => {
            setEditingEvaluator(evaluator);
            setIsWizardOpen(true);
          }}
          onFork={handleFork}
          onDelete={(evaluator) => {
            setEvaluatorToDelete(evaluator);
            setDeleteConfirmOpen(true);
          }}
          onVisibilityChange={handleVisibilityChange}
          onSeedDefaults={supportsAppLevelSeedDefaults && canCreate ? handleSeedDefaults : undefined}
          onToggleHeader={handleToggleHeader}
          isSeeding={isSeeding}
          title="Evaluators"
          description={`Manage the shared evaluator library for ${appMetadata.name}.`}
          headerActions={extraHeaderActions}
          emptyStateActions={extraEmptyStateActions}
          onOpen={onOpenEvaluator}
          canCreate={canCreate}
        />
      )}

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
    </div>
  );
}
