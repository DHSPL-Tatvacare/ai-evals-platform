import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  FileText,
  Plus,
  ArrowLeft,
  GitFork,
  Pencil,
  Shield,
  Star,
} from 'lucide-react';
import { Button, EmptyState, Tabs } from '@/components/ui';
import { evaluatorsRepository } from '@/services/api/evaluatorsApi';
import { notificationService } from '@/services/notifications';
import { cn } from '@/utils';
import { routes } from '@/config/routes';
import type { EvaluatorDefinition, EvaluatorOutputField } from '@/types';
import { CreateEvaluatorOverlay } from '@/features/evals/components/CreateEvaluatorOverlay';

/* ── Helpers ─────────────────────────────────────────────── */

function getDimensionCount(schema: EvaluatorOutputField[]): number {
  return schema.filter((f) => f.type === 'number' && !f.isMainMetric).length;
}

function getTotalPoints(schema: EvaluatorOutputField[]): number {
  return schema
    .filter((f) => f.type === 'number' && !f.isMainMetric)
    .reduce((sum, f) => {
      const match = f.description?.match(/max (\d+)/);
      return sum + (match ? parseInt(match[1], 10) : 0);
    }, 0);
}

function getComplianceCount(schema: EvaluatorOutputField[]): number {
  return schema.filter((f) => f.type === 'boolean').length;
}

function getPassThreshold(schema: EvaluatorOutputField[]): number | null {
  const main = schema.find((f) => f.isMainMetric && f.thresholds);
  return main?.thresholds?.yellow ?? null;
}

function getExcellentThreshold(schema: EvaluatorOutputField[]): number | null {
  const main = schema.find((f) => f.isMainMetric && f.thresholds);
  return main?.thresholds?.green ?? null;
}

function TypeBadge({ evaluator }: { evaluator: EvaluatorDefinition }) {
  if (evaluator.forkedFrom) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-400">
        <GitFork className="h-3 w-3" />
        Forked
      </span>
    );
  }
  if (evaluator.isGlobal) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-purple-500/15 px-2 py-0.5 text-[11px] font-medium text-purple-400">
        <Shield className="h-3 w-3" />
        System
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/15 px-2 py-0.5 text-[11px] font-medium text-blue-400">
      <Star className="h-3 w-3" />
      Custom
    </span>
  );
}

/* ── Main Component ──────────────────────────────────────── */

export function InsideSalesEvaluators() {
  const navigate = useNavigate();
  const { id: paramId } = useParams<{ id: string }>();
  const [evaluators, setEvaluators] = useState<EvaluatorDefinition[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedEval, setSelectedEval] = useState<EvaluatorDefinition | null>(null);
  const [showCreateOverlay, setShowCreateOverlay] = useState(false);
  const [editEval, setEditEval] = useState<EvaluatorDefinition | undefined>(undefined);

  const loadEvaluators = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await evaluatorsRepository.getByAppId('inside-sales');
      setEvaluators(data);

      // If URL has :id, select that evaluator
      if (paramId) {
        const found = data.find((e) => e.id === paramId);
        if (found) setSelectedEval(found);
      }
    } catch {
      notificationService.error('Failed to load evaluators');
    } finally {
      setIsLoading(false);
    }
  }, [paramId]);

  useEffect(() => {
    loadEvaluators();
  }, [loadEvaluators]);

  const handleSeedDefaults = useCallback(async () => {
    try {
      await evaluatorsRepository.seedAppDefaults('inside-sales');
      notificationService.success('Evaluators seeded');
      loadEvaluators();
    } catch {
      notificationService.error('Failed to seed evaluators');
    }
  }, [loadEvaluators]);

  const handleFork = useCallback(async (evalId: string) => {
    try {
      const forked = await evaluatorsRepository.fork(evalId);
      notificationService.success('Evaluator forked');
      setEditEval(forked);
      setShowCreateOverlay(true);
      loadEvaluators();
    } catch {
      notificationService.error('Failed to fork evaluator');
    }
  }, [loadEvaluators]);

  const handleSaveEvaluator = useCallback(async () => {
    setShowCreateOverlay(false);
    setEditEval(undefined);
    loadEvaluators();
  }, [loadEvaluators]);

  // Detail view
  if (selectedEval) {
    return (
      <EvaluatorDetail
        evaluator={selectedEval}
        onBack={() => {
          setSelectedEval(null);
          navigate(routes.insideSales.evaluators);
        }}
        onFork={() => handleFork(selectedEval.id)}
        onEdit={() => {
          setEditEval(selectedEval);
          setShowCreateOverlay(true);
        }}
      />
    );
  }

  // Table view
  return (
    <div className="flex flex-col h-[calc(100vh-var(--header-height))]">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0 pb-4">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">Evaluators</h1>
        <div className="flex items-center gap-2">
          {evaluators.length === 0 && !isLoading && (
            <Button variant="secondary" size="sm" onClick={handleSeedDefaults}>
              Seed Defaults
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setEditEval(undefined);
              setShowCreateOverlay(true);
            }}
          >
            <Plus className="h-3.5 w-3.5" />
            New Evaluator
          </Button>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--border-default)] border-t-[var(--color-brand-accent)]" />
        </div>
      ) : evaluators.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={FileText}
            title="No evaluators yet"
            description="Seed the default GoodFlip QA evaluator or create your own."
            action={{ label: 'Seed Defaults', onClick: handleSeedDefaults }}
          />
        </div>
      ) : (
        <div className="flex-1 overflow-auto rounded-md border border-[var(--border-default)]">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[var(--bg-secondary)] z-10">
              <tr className="border-b border-[var(--border-default)]">
                <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Name</th>
                <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Dimensions</th>
                <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Total Pts</th>
                <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Pass</th>
                <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Type</th>
                <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Compliance</th>
                <th className="w-10 px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {evaluators.map((ev) => (
                <tr
                  key={ev.id}
                  onClick={() => {
                    setSelectedEval(ev);
                    navigate(routes.insideSales.evaluatorDetail(ev.id));
                  }}
                  className="border-b border-[var(--border-subtle)] cursor-pointer transition-colors hover:bg-[var(--interactive-secondary)]"
                >
                  <td className="px-3 py-2.5">
                    <div className="font-medium text-[var(--text-primary)]">{ev.name}</div>
                  </td>
                  <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                    {getDimensionCount(ev.outputSchema)}
                  </td>
                  <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                    {getTotalPoints(ev.outputSchema) || '—'}
                  </td>
                  <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                    {getPassThreshold(ev.outputSchema) ?? '—'}
                  </td>
                  <td className="px-3 py-2.5">
                    <TypeBadge evaluator={ev} />
                  </td>
                  <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                    {getComplianceCount(ev.outputSchema)} gates
                  </td>
                  <td className="w-10 px-2 py-2.5">
                    {ev.isGlobal && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleFork(ev.id);
                        }}
                        className="rounded p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--interactive-secondary)] transition-colors"
                        title="Fork & Edit"
                      >
                        <GitFork className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit overlay */}
      <CreateEvaluatorOverlay
        isOpen={showCreateOverlay}
        onClose={() => {
          setShowCreateOverlay(false);
          setEditEval(undefined);
        }}
        onSave={handleSaveEvaluator}
        context={{ appId: 'inside-sales' }}
        editEvaluator={editEval}
      />
    </div>
  );
}

/* ── Evaluator Detail ────────────────────────────────────── */

function EvaluatorDetail({
  evaluator,
  onBack,
  onFork,
  onEdit,
}: {
  evaluator: EvaluatorDefinition;
  onBack: () => void;
  onFork: () => void;
  onEdit: () => void;
}) {
  const schema = evaluator.outputSchema;
  const dimensions = schema.filter((f) => f.type === 'number' && !f.isMainMetric);
  const complianceGates = schema.filter((f) => f.type === 'boolean');
  const passThreshold = getPassThreshold(schema);
  const excellentThreshold = getExcellentThreshold(schema);

  const scoringTab = {
    id: 'scoring',
    label: 'Scoring Criteria',
    content: (
      <div className="space-y-3 py-3">
        {dimensions.map((dim) => {
          const match = dim.description?.match(/\(max (\d+)\)/);
          const maxPts = match ? match[1] : '?';
          const name = dim.description?.replace(/\s*\(max \d+\)/, '') || dim.key;
          return (
            <div
              key={dim.key}
              className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-[var(--text-primary)]">{name}</span>
                <span className="rounded-full bg-[var(--color-brand-accent)]/20 px-2 py-0.5 text-[11px] font-bold text-[var(--text-brand)]">
                  {maxPts} pts
                </span>
              </div>
              {dim.thresholds && (
                <div className="mt-1.5 flex gap-2 text-[10px] text-[var(--text-muted)]">
                  <span>Green ≥ {dim.thresholds.green}</span>
                  <span>Yellow ≥ {dim.thresholds.yellow}</span>
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
        {/* Compliance gates */}
        {complianceGates.length > 0 && (
          <div className="rounded-md border border-red-500/20 bg-red-500/5 p-3">
            <div className="flex items-center gap-1.5 mb-2">
              <Shield className="h-3.5 w-3.5 text-red-400" />
              <span className="text-xs font-semibold text-red-400">Compliance Gates</span>
            </div>
            <ul className="space-y-1.5">
              {complianceGates.map((gate) => (
                <li key={gate.key} className="text-xs text-[var(--text-secondary)] flex items-start gap-2">
                  <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-red-400 shrink-0" />
                  {gate.description}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Thresholds */}
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-[var(--text-primary)]">Interpretation Bands</h3>
          <div className="grid grid-cols-2 gap-2">
            <ThresholdCard color="emerald" label="Strong" range="80-100" description="Ready for independent calling" />
            <ThresholdCard color="blue" label="Good" range="65-79" description="Minor coaching points" />
            <ThresholdCard color="amber" label="Needs Work" range="50-64" description="Structured coaching required" />
            <ThresholdCard color="red" label="Poor" range="Below 50" description="Re-training recommended" />
          </div>
        </div>

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

  return (
    <div className="flex flex-col h-[calc(100vh-var(--header-height))] gap-4">
      {/* Back button */}
      <div className="shrink-0">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Evaluators
        </button>
      </div>

      {/* Header */}
      <div className="shrink-0 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-[var(--text-primary)]">{evaluator.name}</h1>
            <TypeBadge evaluator={evaluator} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          {evaluator.isGlobal ? (
            <Button variant="secondary" size="sm" onClick={onFork}>
              <GitFork className="h-3.5 w-3.5" />
              Fork & Edit
            </Button>
          ) : (
            <Button variant="secondary" size="sm" onClick={onEdit}>
              <Pencil className="h-3.5 w-3.5" />
              Edit
            </Button>
          )}
        </div>
      </div>

      {/* Metadata bar */}
      <div className="shrink-0 flex flex-wrap gap-4 text-xs text-[var(--text-muted)]">
        <span>{getDimensionCount(schema)} dimensions</span>
        <span>{getTotalPoints(schema)} total pts</span>
        {passThreshold !== null && <span>Pass ≥ {passThreshold}</span>}
        {excellentThreshold !== null && <span>Excellent ≥ {excellentThreshold}</span>}
        <span>{getComplianceCount(schema)} compliance gates</span>
      </div>

      {/* Tabs */}
      <Tabs tabs={[scoringTab, complianceTab]} defaultTab="scoring" fillHeight />
    </div>
  );
}

function ThresholdCard({
  color,
  label,
  range,
  description,
}: {
  color: string;
  label: string;
  range: string;
  description: string;
}) {
  const colorMap: Record<string, string> = {
    emerald: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
    blue: 'bg-blue-500/10 border-blue-500/20 text-blue-400',
    amber: 'bg-amber-500/10 border-amber-500/20 text-amber-400',
    red: 'bg-red-500/10 border-red-500/20 text-red-400',
  };
  return (
    <div className={cn('rounded-md border p-2.5', colorMap[color])}>
      <div className="text-xs font-semibold">{label}</div>
      <div className="text-[11px] font-mono">{range}</div>
      <div className="text-[10px] mt-0.5 opacity-80">{description}</div>
    </div>
  );
}
