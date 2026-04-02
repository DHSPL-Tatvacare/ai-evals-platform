import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { BarChart3, ChevronDown, Library, Plus, Star } from 'lucide-react';
import { PermissionGate } from '@/components/auth/PermissionGate';
import { Button, ConfirmDialog, EmptyState, Skeleton } from '@/components/ui';
import { CreateEvaluatorOverlay, EvaluatorCard, EvaluatorRegistryPicker } from '@/features/evals/components';
import { useCurrentAppConfig, useCurrentAppId, useCurrentAppMetadata } from '@/hooks';
import { notificationService } from '@/services/notifications';
import { useEvaluatorsStore } from '@/stores';
import { cn } from '@/utils';
import type { EvaluatorDefinition, EvaluatorContext } from '@/types';

type EvaluatorCatalogFilter = 'registry' | 'all';

interface AppEvaluatorsPageProps {
  extraHeaderActions?: ReactNode;
  extraEmptyStateActions?: ReactNode;
  onOpenEvaluator?: (evaluator: EvaluatorDefinition) => void;
}

function isRegistryEvaluator(evaluator: EvaluatorDefinition): boolean {
  return Boolean(evaluator.isGlobal || evaluator.isBuiltIn);
}

function isVisibleOnAppPage(evaluator: EvaluatorDefinition): boolean {
  return !evaluator.listingId || isRegistryEvaluator(evaluator);
}

export function AppEvaluatorsPage({
  extraHeaderActions,
  extraEmptyStateActions,
  onOpenEvaluator,
}: AppEvaluatorsPageProps) {
  const appId = useCurrentAppId();
  const appConfig = useCurrentAppConfig();
  const appMetadata = useCurrentAppMetadata();
  const [filter, setFilter] = useState<EvaluatorCatalogFilter>('registry');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingEvaluator, setEditingEvaluator] = useState<EvaluatorDefinition | undefined>();
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [showRegistryPicker, setShowRegistryPicker] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [evaluatorToDelete, setEvaluatorToDelete] = useState<string | null>(null);
  const [isSeeding, setIsSeeding] = useState(false);

  const {
    evaluators,
    isLoaded,
    currentListingId,
    currentAppId,
    loadAppEvaluators,
    addEvaluator,
    updateEvaluator,
    deleteEvaluator,
    setGlobal,
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

  const pageEvaluators = useMemo(
    () => evaluators.filter(isVisibleOnAppPage),
    [evaluators],
  );

  const filteredEvaluators = useMemo(
    () =>
      filter === 'registry'
        ? pageEvaluators.filter(isRegistryEvaluator)
        : pageEvaluators,
    [filter, pageEvaluators],
  );

  const context: EvaluatorContext = useMemo(
    () => ({
      appId,
    }),
    [appId],
  );

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

  const handleEdit = (evaluator: EvaluatorDefinition) => {
    setEditingEvaluator(evaluator);
    setIsModalOpen(true);
  };

  const handleDelete = (evaluatorId: string) => {
    setEvaluatorToDelete(evaluatorId);
    setDeleteConfirmOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!evaluatorToDelete) {
      return;
    }

    await deleteEvaluator(evaluatorToDelete);
    notificationService.success('Evaluator deleted');
    setDeleteConfirmOpen(false);
    setEvaluatorToDelete(null);
  };

  const handleToggleHeader = async (evaluatorId: string, showInHeader: boolean) => {
    const evaluator = evaluators.find((entry) => entry.id === evaluatorId);
    if (!evaluator) {
      return;
    }

    await updateEvaluator({
      ...evaluator,
      showInHeader,
      updatedAt: new Date(),
    });

    notificationService.success(
      showInHeader
        ? 'Evaluator added to header'
        : 'Evaluator removed from header',
    );
  };

  const handleToggleGlobal = async (evaluatorId: string, isGlobal: boolean) => {
    await setGlobal(evaluatorId, isGlobal);
    notificationService.success(
      isGlobal
        ? 'Evaluator added to Registry'
        : 'Evaluator removed from Registry',
    );
  };

  const handleFork = async (sourceId: string) => {
    const forked = await forkEvaluator(sourceId);
    notificationService.success(`Forked evaluator: ${forked.name}`);
  };

  const handleSeedDefaults = async () => {
    if (!supportsAppLevelSeedDefaults) {
      return;
    }

    setIsSeeding(true);
    try {
      const seeded = await seedAppDefaults(appId);
      notificationService.success(`Added ${seeded.length} default evaluators`);
    } catch (err) {
      notificationService.error(
        err instanceof Error ? err.message : 'Failed to seed defaults',
      );
    } finally {
      setIsSeeding(false);
    }
  };

  const openCreateOverlay = () => {
    setEditingEvaluator(undefined);
    setIsModalOpen(true);
    setShowAddMenu(false);
  };

  const openRegistryPicker = () => {
    setShowRegistryPicker(true);
    setShowAddMenu(false);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">Evaluators</h1>
          <p className="text-sm text-[var(--text-secondary)]">
            Manage the shared evaluator catalog for {appMetadata.name}.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start">
          {extraHeaderActions}
          {supportsAppLevelSeedDefaults && (
            <PermissionGate action="resource:create">
              <Button
                variant="secondary"
                onClick={handleSeedDefaults}
                isLoading={isSeeding}
                icon={Star}
              >
                Seed Defaults
              </Button>
            </PermissionGate>
          )}

          <div className="relative">
            <PermissionGate action="resource:create">
              <Button onClick={() => setShowAddMenu((open) => !open)}>
                <Plus className="h-4 w-4" />
                Add Evaluator
                <ChevronDown className="h-4 w-4" />
              </Button>
            </PermissionGate>

            {showAddMenu && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowAddMenu(false)}
                />
                <div className="absolute right-0 z-20 mt-1 min-w-[180px] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] py-1 shadow-lg">
                  <button
                    onClick={openCreateOverlay}
                    className="w-full px-4 py-2 text-left text-sm text-[var(--text-primary)] transition-colors hover:bg-[var(--interactive-secondary)]"
                  >
                    Create New
                  </button>
                  <button
                    onClick={openRegistryPicker}
                    className="w-full px-4 py-2 text-left text-sm text-[var(--text-primary)] transition-colors hover:bg-[var(--interactive-secondary)]"
                  >
                    Browse Registry
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="inline-flex w-fit rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-1">
        {(['registry', 'all'] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={cn(
              'rounded-[6px] px-3 py-1.5 text-sm font-medium transition-colors',
              filter === value
                ? 'bg-[var(--interactive-primary)] text-[var(--text-on-color)]'
                : 'text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]',
            )}
          >
            {value === 'registry' ? 'Registry' : 'All'}
          </button>
        ))}
      </div>

      {!isLoaded ? (
        <div className="grid grid-cols-1 gap-4 pt-6 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full rounded-xl" />
          ))}
        </div>
      ) : filteredEvaluators.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <EmptyState
            icon={filter === 'registry' ? Library : BarChart3}
            title={filter === 'registry' ? 'No evaluators in the registry yet' : 'No evaluators yet'}
            description={
              filter === 'registry'
                ? 'Create a shared evaluator or fork one into your catalog to get started.'
                : 'Create an app-level evaluator or switch back to the registry view.'
            }
            className="w-full max-w-xl"
          >
            <PermissionGate action="resource:create">
              <div className="flex flex-wrap items-center justify-center gap-2">
                {extraEmptyStateActions}
                <Button onClick={openCreateOverlay}>
                  <Plus className="h-4 w-4" />
                  Create Evaluator
                </Button>
                <Button variant="secondary" onClick={openRegistryPicker}>
                  Browse Registry
                </Button>
                {supportsAppLevelSeedDefaults && (
                  <Button
                    variant="secondary"
                    onClick={handleSeedDefaults}
                    isLoading={isSeeding}
                    icon={Star}
                  >
                    Seed Defaults
                  </Button>
                )}
              </div>
            </PermissionGate>
          </EmptyState>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredEvaluators.map((evaluator) => (
            <EvaluatorCard
              key={evaluator.id}
              evaluator={evaluator}
              onOpen={onOpenEvaluator}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onToggleHeader={handleToggleHeader}
              onToggleGlobal={handleToggleGlobal}
            />
          ))}
        </div>
      )}

      <CreateEvaluatorOverlay
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingEvaluator(undefined);
        }}
        onSave={handleSave}
        context={context}
        editEvaluator={editingEvaluator}
        defaultIsGlobal
      />

      <EvaluatorRegistryPicker
        isOpen={showRegistryPicker}
        onClose={() => setShowRegistryPicker(false)}
        appId={appId}
        onFork={handleFork}
      />

      <ConfirmDialog
        isOpen={deleteConfirmOpen}
        onClose={() => {
          setDeleteConfirmOpen(false);
          setEvaluatorToDelete(null);
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
