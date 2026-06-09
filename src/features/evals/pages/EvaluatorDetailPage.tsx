import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { GitFork, Info, Pencil, Shield, Star } from 'lucide-react';
import { Button, EmptyState, LoadingState, PageSurface, Tabs, Tooltip } from '@/components/ui';
import { CreateEvaluatorWizard } from '@/features/evals/components/CreateEvaluatorWizard';
import { isSystemEvaluator } from '@/features/evals/utils/evaluatorMetadata';
import { evaluatorsListForApp } from '@/config/routes';
import { resolvePageMetadata } from '@/config/pageMetadata';
import { notificationService } from '@/services/notifications';
import { useCurrentAppConfig, useCurrentAppId } from '@/hooks';
import { useEvaluatorsStore } from '@/stores';
import { useAuthStore } from '@/stores/authStore';
import { cn } from '@/utils';
import type {
  EvaluatorDefinition,
  EvaluatorDetailBand,
  EvaluatorDetailBandColor,
  EvaluatorOutputField,
} from '@/types';

function getDimensionCount(schema: EvaluatorOutputField[]): number {
  return schema.filter((field) => field.type === 'number' && !field.isMainMetric).length;
}

function getTotalPoints(schema: EvaluatorOutputField[]): number {
  return schema
    .filter((field) => field.type === 'number' && !field.isMainMetric)
    .reduce((sum, field) => {
      const match = field.description?.match(/max (\d+)/);
      return sum + (match ? parseInt(match[1], 10) : 0);
    }, 0);
}

function getComplianceCount(schema: EvaluatorOutputField[]): number {
  return schema.filter((field) => field.type === 'boolean').length;
}

function getPassThreshold(schema: EvaluatorOutputField[]): number | null {
  const mainMetric = schema.find((field) => field.isMainMetric && field.thresholds);
  return mainMetric?.thresholds?.yellow ?? null;
}

function getExcellentThreshold(schema: EvaluatorOutputField[]): number | null {
  const mainMetric = schema.find((field) => field.isMainMetric && field.thresholds);
  return mainMetric?.thresholds?.green ?? null;
}

function TypeBadge({ evaluator }: { evaluator: EvaluatorDefinition }) {
  if (evaluator.forkedFrom) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-warning)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-warning)]">
        <GitFork className="h-3 w-3" />
        Forked
      </span>
    );
  }

  if (isSystemEvaluator(evaluator)) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-accent-purple)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-accent-purple)]">
        <Shield className="h-3 w-3" />
        System
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-info)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-info)]">
      <Star className="h-3 w-3" />
      Custom
    </span>
  );
}

export function EvaluatorDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [showCreateWizard, setShowCreateWizard] = useState(false);
  const [editEvaluator, setEditEvaluator] = useState<EvaluatorDefinition | undefined>();
  const currentUser = useAuthStore((state) => state.user);
  const appId = useCurrentAppId();
  const appConfig = useCurrentAppConfig();
  const { icon: pageIcon } = resolvePageMetadata('evaluatorDetail', appConfig);
  const backTarget = evaluatorsListForApp(appId);
  const back = backTarget ? { to: backTarget, label: 'Evaluators' } : undefined;
  const bands = appConfig.evaluatorDetail?.interpretationBands ?? [];

  const {
    evaluators,
    isLoaded,
    currentAppId,
    currentListingId,
    loadAppEvaluators,
    updateEvaluator,
    forkEvaluator,
  } = useEvaluatorsStore();

  useEffect(() => {
    if (!isLoaded || currentAppId !== appId || currentListingId !== null) {
      loadAppEvaluators(appId);
    }
  }, [appId, currentAppId, currentListingId, isLoaded, loadAppEvaluators]);

  const evaluator = useMemo(
    () => evaluators.find((entry) => entry.id === id),
    [evaluators, id],
  );
  const canEdit = Boolean(
    evaluator &&
    currentUser &&
    evaluator.tenantId === currentUser.tenantId &&
    evaluator.userId === currentUser.id,
  );

  const handleFork = async () => {
    if (!evaluator) {
      return;
    }

    const forked = await forkEvaluator(evaluator.id);
    notificationService.success(`Forked evaluator: ${forked.name}`);
    setEditEvaluator(forked);
    setShowCreateWizard(true);
  };

  const handleSave = async (nextEvaluator: EvaluatorDefinition) => {
    await updateEvaluator(nextEvaluator);
    notificationService.success('Evaluator updated');
    setEditEvaluator(undefined);
  };

  if (!isLoaded) {
    return (
      <PageSurface icon={pageIcon} title="Evaluator" back={back} showHeader={false}>
        <LoadingState />
      </PageSurface>
    );
  }

  if (!evaluator) {
    return (
      <PageSurface icon={pageIcon} title="Evaluator" back={back}>
        <EmptyState
          icon={Pencil}
          title="Evaluator not found"
          description="This evaluator does not exist or is no longer available."
          action={
            backTarget
              ? {
                  label: 'Back to Evaluators',
                  onClick: () => navigate(backTarget),
                }
              : undefined
          }
          className="w-full max-w-md"
          fill
        />
      </PageSurface>
    );
  }

  const schema = evaluator.outputSchema;
  const dimensions = schema.filter((field) => field.type === 'number' && !field.isMainMetric);
  const complianceGates = schema.filter((field) => field.type === 'boolean');
  const passThreshold = getPassThreshold(schema);
  const excellentThreshold = getExcellentThreshold(schema);

  const scoringTab = {
    id: 'scoring',
    label: 'Scoring Criteria',
    content: (
      <div className="space-y-3 py-3">
        {dimensions.map((dimension) => {
          const match = dimension.description?.match(/\(max (\d+)\)/);
          const maxPoints = match ? match[1] : '?';
          const name = dimension.description?.replace(/\s*\(max \d+\)/, '') || dimension.key;

          return (
            <div
              key={dimension.key}
              className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-[var(--text-primary)]">{name}</span>
                <span className="rounded-full bg-[var(--color-brand-accent)]/20 px-2 py-0.5 text-[11px] font-bold text-[var(--text-brand)]">
                  {maxPoints} pts
                </span>
              </div>
              {dimension.thresholds && (
                <div className="mt-1.5 flex gap-2 text-[10px] text-[var(--text-muted)]">
                  <span>Green ≥ {dimension.thresholds.green}</span>
                  <span>Yellow ≥ {dimension.thresholds.yellow}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    ),
  };

  const complianceTab = {
    id: 'compliance',
    label: 'Compliance & Thresholds',
    content: (
      <div className="space-y-4 py-3">
        {complianceGates.length > 0 && (
          <div className="rounded-md border border-[var(--border-error)] bg-[var(--surface-error)] p-3">
            <div className="mb-2 flex items-center gap-1.5">
              <Shield className="h-3.5 w-3.5 text-[var(--color-error)]" />
              <span className="text-xs font-semibold text-[var(--color-error)]">Compliance Gates</span>
            </div>
            <ul className="space-y-1.5">
              {complianceGates.map((gate) => (
                <li key={gate.key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-error)]" />
                  {gate.description}
                </li>
              ))}
            </ul>
          </div>
        )}

        {bands.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-[var(--text-primary)]">Interpretation Bands</h3>
            <div className="grid grid-cols-2 gap-2">
              {bands.map((band) => (
                <ThresholdCard key={band.label} band={band} />
              ))}
            </div>
          </div>
        )}

        {passThreshold !== null && excellentThreshold !== null && (
          <div className="text-xs text-[var(--text-muted)]">
            Pass threshold: <strong className="text-[var(--text-primary)]">{passThreshold}</strong>
            {' · '}
            Excellent threshold: <strong className="text-[var(--text-primary)]">{excellentThreshold}</strong>
          </div>
        )}
      </div>
    ),
  };

  const metaTooltip = (
    <div className="flex flex-col gap-1 text-xs text-[var(--text-secondary)]">
      <div><span className="text-[var(--text-muted)]">Dimensions </span>{getDimensionCount(schema)}</div>
      <div><span className="text-[var(--text-muted)]">Total pts </span>{getTotalPoints(schema)}</div>
      {passThreshold !== null && (
        <div><span className="text-[var(--text-muted)]">Pass ≥ </span>{passThreshold}</div>
      )}
      {excellentThreshold !== null && (
        <div><span className="text-[var(--text-muted)]">Excellent ≥ </span>{excellentThreshold}</div>
      )}
      <div><span className="text-[var(--text-muted)]">Compliance gates </span>{getComplianceCount(schema)}</div>
    </div>
  );

  const subtitle = (
    <>
      <TypeBadge evaluator={evaluator} />
      <Tooltip content={metaTooltip} closeDelay={150}>
        <Info className="h-3.5 w-3.5 text-[var(--text-muted)] cursor-help" />
      </Tooltip>
    </>
  );

  const actions = !canEdit ? (
    <Button variant="secondary" size="sm" onClick={handleFork}>
      <GitFork className="h-3.5 w-3.5" />
      Fork & Edit
    </Button>
  ) : (
    <Button
      variant="secondary"
      size="sm"
      onClick={() => {
        setEditEvaluator(evaluator);
        setShowCreateWizard(true);
      }}
    >
      <Pencil className="h-3.5 w-3.5" />
      Edit
    </Button>
  );

  return (
    <>
      <PageSurface
        icon={pageIcon}
        title={evaluator.name}
        subtitle={subtitle}
        back={back}
        actions={actions}
      >
        <Tabs tabs={[scoringTab, complianceTab]} defaultTab="scoring" fillHeight />
      </PageSurface>

      {showCreateWizard ? (
        <CreateEvaluatorWizard
          isOpen={showCreateWizard}
          onClose={() => {
            setShowCreateWizard(false);
            setEditEvaluator(undefined);
          }}
          onSave={handleSave}
          context={{ appId }}
          editEvaluator={editEvaluator}
        />
      ) : null}
    </>
  );
}

const BAND_COLOR_CLASSES: Record<EvaluatorDetailBandColor, string> = {
  emerald: 'bg-[var(--surface-success)] border-[var(--border-success)] text-[var(--color-success)]',
  blue: 'bg-[var(--surface-info)] border-[var(--border-info)] text-[var(--color-info)]',
  amber: 'bg-[var(--surface-warning)] border-[var(--border-warning)] text-[var(--color-warning)]',
  red: 'bg-[var(--surface-error)] border-[var(--border-error)] text-[var(--color-error)]',
};

function ThresholdCard({ band }: { band: EvaluatorDetailBand }) {
  return (
    <div className={cn('rounded-md border p-2.5', BAND_COLOR_CLASSES[band.color])}>
      <div className="text-xs font-semibold">{band.label}</div>
      <div className="text-[11px] font-mono">{band.range}</div>
      <div className="mt-0.5 text-[10px] opacity-80">{band.description}</div>
    </div>
  );
}
