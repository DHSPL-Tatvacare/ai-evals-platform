import { useEffect, useMemo, useState } from 'react';
import {
  Info,
  Library,
  Loader2,
  Pin,
  PinOff,
  Plus,
  Save,
  Sparkles,
  Trash2,
} from 'lucide-react';

import {
  Button,
  Card,
  Input,
  MultiSelect,
  type MultiSelectOption,
} from '@/components/ui';
import {
  adversarialConfigApi,
  type AdversarialGoal,
  type AdversarialTrait,
} from '@/services/api/adversarialConfigApi';
import {
  adversarialTestCasesApi,
  type AdversarialSavedCase,
} from '@/services/api/adversarialTestCasesApi';
import { SettingsSlideOver } from '@/features/settings/components/SettingsSlideOver';
import { notificationService } from '@/services/notifications';
import { humanize } from '@/utils/evalFormatters';

type FlowMode = 'single' | 'multi';
export type AdversarialCaseMode = 'generate' | 'saved' | 'hybrid';
export type ManualCaseDifficulty = 'EASY' | 'MEDIUM' | 'HARD';

export interface AdversarialManualCaseInput {
  name?: string;
  description?: string;
  syntheticInput: string;
  difficulty: ManualCaseDifficulty;
  goalFlow: string[];
  activeTraits: string[];
  expectedChallenges: string[];
}

interface TestConfigStepProps {
  caseMode: AdversarialCaseMode;
  testCount: number;
  turnDelay: number;
  caseDelay: number;
  selectedGoals: string[];
  flowMode: FlowMode;
  extraInstructions: string;
  selectedSavedCaseIds: string[];
  includePinnedCases: boolean;
  manualCases: AdversarialManualCaseInput[];
  onCaseModeChange: (mode: AdversarialCaseMode) => void;
  onTestCountChange: (count: number) => void;
  onTurnDelayChange: (delay: number) => void;
  onCaseDelayChange: (delay: number) => void;
  onGoalsChange: (goals: string[]) => void;
  onFlowModeChange: (mode: FlowMode) => void;
  onExtraInstructionsChange: (instructions: string) => void;
  onSavedCasesChange: (caseIds: string[]) => void;
  onIncludePinnedCasesChange: (enabled: boolean) => void;
  onManualCasesChange: (cases: AdversarialManualCaseInput[]) => void;
}

const DIFFICULTY_LEVELS: Array<{ value: ManualCaseDifficulty; label: string }> = [
  { value: 'EASY', label: 'Easy' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'HARD', label: 'Hard' },
];

const CASE_MODE_OPTIONS: Array<{
  value: AdversarialCaseMode;
  label: string;
  description: string;
}> = [
  {
    value: 'generate',
    label: 'Generate Fresh',
    description: 'Create new exploratory cases from the goal catalog.',
  },
  {
    value: 'saved',
    label: 'Use Saved Cases',
    description: 'Run selected regression cases and pinned cases without generation.',
  },
  {
    value: 'hybrid',
    label: 'Hybrid',
    description: 'Mix generated exploration with saved and pinned cases.',
  },
];

const EMPTY_DRAFT: AdversarialManualCaseInput = {
  name: '',
  description: '',
  syntheticInput: '',
  difficulty: 'MEDIUM',
  goalFlow: [],
  activeTraits: [],
  expectedChallenges: [],
};

function splitChallenges(raw: string): string[] {
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function manualCaseKey(testCase: AdversarialManualCaseInput): string {
  return [
    testCase.syntheticInput.trim().toLowerCase(),
    testCase.difficulty,
    [...testCase.goalFlow].sort().join(','),
    [...testCase.activeTraits].sort().join(','),
  ].join('|');
}

export function TestConfigStep({
  caseMode,
  testCount,
  turnDelay,
  caseDelay,
  selectedGoals,
  flowMode,
  extraInstructions,
  selectedSavedCaseIds,
  includePinnedCases,
  manualCases,
  onCaseModeChange,
  onTestCountChange,
  onTurnDelayChange,
  onCaseDelayChange,
  onGoalsChange,
  onFlowModeChange,
  onExtraInstructionsChange,
  onSavedCasesChange,
  onIncludePinnedCasesChange,
  onManualCasesChange,
}: TestConfigStepProps) {
  const [goals, setGoals] = useState<AdversarialGoal[]>([]);
  const [traits, setTraits] = useState<AdversarialTrait[]>([]);
  const [savedCases, setSavedCases] = useState<AdversarialSavedCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [testCountLocal, setTestCountLocal] = useState<string | null>(null);
  const [testCountError, setTestCountError] = useState('');
  const [librarySearch, setLibrarySearch] = useState('');
  const [onlyPinnedLibrary, setOnlyPinnedLibrary] = useState(false);
  const [libraryBusyId, setLibraryBusyId] = useState<string | null>(null);
  const [savingDraft, setSavingDraft] = useState(false);
  const [draft, setDraft] = useState<AdversarialManualCaseInput>(EMPTY_DRAFT);
  const [draftChallengesText, setDraftChallengesText] = useState('');
  const [saveDraftPinned, setSaveDraftPinned] = useState(false);
  const [libraryOverlayOpen, setLibraryOverlayOpen] = useState(false);
  const [manualCaseOverlayOpen, setManualCaseOverlayOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      adversarialConfigApi.get(),
      adversarialTestCasesApi.list(),
    ])
      .then(([config, cases]) => {
        if (cancelled) return;
        const enabledGoals = config.goals.filter((goal) => goal.enabled);
        const enabledTraits = config.traits.filter((trait) => trait.enabled);
        setGoals(enabledGoals);
        setTraits(enabledTraits);
        setSavedCases(cases);
        if (selectedGoals.length === 0 && enabledGoals.length > 0) {
          onGoalsChange(enabledGoals.map((goal) => goal.id));
        }
      })
      .catch((err) => {
        if (cancelled) return;
        notificationService.error(
          err instanceof Error ? err.message : 'Failed to load adversarial test configuration.',
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const goalOptions = useMemo<MultiSelectOption[]>(
    () => goals.map((goal) => ({ value: goal.id, label: goal.label || humanize(goal.id) })),
    [goals],
  );
  const traitOptions = useMemo<MultiSelectOption[]>(
    () => traits.map((trait) => ({ value: trait.id, label: trait.label || humanize(trait.id) })),
    [traits],
  );

  const filteredLibraryCases = useMemo(() => {
    const q = librarySearch.trim().toLowerCase();
    return savedCases.filter((testCase) => {
      if (onlyPinnedLibrary && !testCase.isPinned) return false;
      if (!q) return true;
      const haystack = [
        testCase.name,
        testCase.syntheticInput,
        testCase.goalFlow.join(' '),
        testCase.activeTraits.join(' '),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [librarySearch, onlyPinnedLibrary, savedCases]);

  const selectedSavedCases = useMemo(
    () => savedCases.filter((testCase) => selectedSavedCaseIds.includes(testCase.id)),
    [savedCases, selectedSavedCaseIds],
  );

  const manualCaseCount = manualCases.length;
  const selectedSavedCount = selectedSavedCaseIds.length;
  const pinnedAvailableCount = savedCases.filter((testCase) => testCase.isPinned).length;

  const canAddDraftToRun =
    draft.syntheticInput.trim().length > 0 && draft.goalFlow.length > 0;
  const manualDraftIsDirty =
    JSON.stringify(draft) !== JSON.stringify(EMPTY_DRAFT)
    || draftChallengesText.trim().length > 0
    || saveDraftPinned;

  const generateEnabled = caseMode !== 'saved';
  const libraryEnabled = caseMode !== 'generate';

  const removeManualCase = (index: number) => {
    onManualCasesChange(manualCases.filter((_, currentIndex) => currentIndex !== index));
  };

  const addDraftToRun = () => {
    if (!canAddDraftToRun) return;
    const nextDraft: AdversarialManualCaseInput = {
      ...draft,
      name: draft.name?.trim() || '',
      description: draft.description?.trim() || '',
      syntheticInput: draft.syntheticInput.trim(),
      goalFlow: [...draft.goalFlow],
      activeTraits: [...draft.activeTraits],
      expectedChallenges: splitChallenges(draftChallengesText),
    };
    const nextKey = manualCaseKey(nextDraft);
    if (manualCases.some((testCase) => manualCaseKey(testCase) === nextKey)) {
      notificationService.info('That run-only case is already included.');
      return;
    }
    onManualCasesChange([...manualCases, nextDraft]);
    setDraft(EMPTY_DRAFT);
    setDraftChallengesText('');
    setSaveDraftPinned(false);
    setManualCaseOverlayOpen(false);
  };

  const saveDraftToLibrary = async () => {
    if (!canAddDraftToRun) return;
    setSavingDraft(true);
    try {
      const created = await adversarialTestCasesApi.create({
        name: draft.name?.trim() || undefined,
        description: draft.description?.trim() || undefined,
        syntheticInput: draft.syntheticInput.trim(),
        difficulty: draft.difficulty,
        goalFlow: draft.goalFlow,
        activeTraits: draft.activeTraits,
        expectedChallenges: splitChallenges(draftChallengesText),
        isPinned: saveDraftPinned,
        sourceKind: 'manual',
      });
      setSavedCases((current) => [created, ...current]);
      if (!selectedSavedCaseIds.includes(created.id)) {
        onSavedCasesChange([...selectedSavedCaseIds, created.id]);
      }
      notificationService.success('Saved adversarial test case.');
      setDraft(EMPTY_DRAFT);
      setDraftChallengesText('');
      setSaveDraftPinned(false);
      setManualCaseOverlayOpen(false);
    } catch (err) {
      notificationService.error(
        err instanceof Error ? err.message : 'Failed to save adversarial test case.',
      );
    } finally {
      setSavingDraft(false);
    }
  };

  const toggleSavedCaseSelection = (caseId: string) => {
    if (selectedSavedCaseIds.includes(caseId)) {
      onSavedCasesChange(selectedSavedCaseIds.filter((currentId) => currentId !== caseId));
      return;
    }
    onSavedCasesChange([...selectedSavedCaseIds, caseId]);
  };

  const toggleCasePinned = async (testCase: AdversarialSavedCase) => {
    setLibraryBusyId(testCase.id);
    try {
      const updated = await adversarialTestCasesApi.update(testCase.id, {
        isPinned: !testCase.isPinned,
      });
      setSavedCases((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (err) {
      notificationService.error(
        err instanceof Error ? err.message : 'Failed to update saved case.',
      );
    } finally {
      setLibraryBusyId(null);
    }
  };

  const deleteSavedCase = async (testCase: AdversarialSavedCase) => {
    setLibraryBusyId(testCase.id);
    try {
      await adversarialTestCasesApi.delete(testCase.id);
      setSavedCases((current) => current.filter((item) => item.id !== testCase.id));
      if (selectedSavedCaseIds.includes(testCase.id)) {
        onSavedCasesChange(selectedSavedCaseIds.filter((currentId) => currentId !== testCase.id));
      }
    } catch (err) {
      notificationService.error(
        err instanceof Error ? err.message : 'Failed to delete saved case.',
      );
    } finally {
      setLibraryBusyId(null);
    }
  };

  return (
    <div className="space-y-5">
      <Card className="space-y-4" hoverable={false}>
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-[var(--text-brand)]" />
          <div>
            <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">
              Case Source
            </h3>
            <p className="text-[11px] text-[var(--text-muted)]">
              Choose whether this run explores fresh cases, replays saved regressions, or mixes both.
            </p>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-3">
          {CASE_MODE_OPTIONS.map((option) => {
            const active = caseMode === option.value;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => onCaseModeChange(option.value)}
                className={`rounded-[6px] border px-3 py-3 text-left transition-colors ${
                  active
                    ? 'border-[var(--border-brand)] bg-[var(--color-brand-accent)]/10'
                    : 'border-[var(--border-subtle)] bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)]'
                }`}
              >
                <p className="text-[12px] font-semibold text-[var(--text-primary)]">
                  {option.label}
                </p>
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-muted)]">
                  {option.description}
                </p>
              </button>
            );
          })}
        </div>

        <div className="grid gap-2 md:grid-cols-4">
          <SummaryPill label="Generated" value={generateEnabled ? `${testCount}` : 'Off'} />
          <SummaryPill label="Saved Selected" value={selectedSavedCount} />
          <SummaryPill label="Pinned Available" value={pinnedAvailableCount} />
          <SummaryPill label="Run-Only Cases" value={manualCaseCount} />
        </div>
      </Card>

      {generateEnabled && (
        <Card className="space-y-5" hoverable={false}>
          <SectionHeader
            title="Generated Cases"
            description="Use the catalog to steer newly generated cases without hardcoding the test suite."
          />

          <div>
            <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
              Number of Generated Cases
            </label>
            <Input
              type="number"
              min={5}
              max={50}
              value={testCountLocal ?? String(testCount)}
              error={testCountError}
              onFocus={() => setTestCountLocal(String(testCount))}
              onChange={(e) => {
                const raw = e.target.value;
                setTestCountLocal(raw);
                const parsed = parseInt(raw, 10);
                if (raw === '' || Number.isNaN(parsed)) {
                  setTestCountError('');
                } else if (parsed < 5) {
                  setTestCountError('Minimum is 5');
                } else if (parsed > 50) {
                  setTestCountError('Maximum is 50');
                } else {
                  setTestCountError('');
                  onTestCountChange(parsed);
                }
              }}
              onBlur={() => {
                const parsed = parseInt(testCountLocal ?? '', 10);
                if (Number.isNaN(parsed) || parsed < 5) {
                  setTestCountLocal(null);
                  setTestCountError('');
                  return;
                }
                onTestCountChange(Math.min(parsed, 50));
                setTestCountLocal(null);
                setTestCountError('');
              }}
            />
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              Generated cases stay capped at 50 for now. Saved and pinned cases can extend coverage beyond that.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
                Goals
              </label>
              {loading ? (
                <LoadingRow label="Loading goals..." />
              ) : (
                <MultiSelect
                  values={selectedGoals}
                  onChange={(values) => {
                    if (values.length === 0 && goals.length > 0) {
                      onGoalsChange([goals[0].id]);
                      return;
                    }
                    onGoalsChange(values);
                  }}
                  options={goalOptions}
                  placeholder="Select goals"
                />
              )}
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                Generated cases will target these goals. At least one goal must stay selected.
              </p>
            </div>

            <div>
              <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
                Flow Mode
              </label>
              <div className="flex gap-2">
                {(['single', 'multi'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => onFlowModeChange(mode)}
                    className={`px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors ${
                      flowMode === mode
                        ? 'bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)] ring-1 ring-[var(--color-brand-accent)]/40'
                        : 'bg-[var(--bg-secondary)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                    }`}
                  >
                    {mode === 'single' ? 'Single Goal' : 'Multi-Goal'}
                  </button>
                ))}
              </div>
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                {flowMode === 'single'
                  ? 'Each generated case focuses on one goal.'
                  : 'Generated conversations can chain multiple goals in one session.'}
              </p>
            </div>
          </div>

          <div className="rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
            <div className="flex items-center gap-1.5 mb-2">
              <Info className="h-3.5 w-3.5 text-[var(--text-muted)]" />
              <span className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                Difficulty Distribution
              </span>
            </div>
            <div className="flex gap-3">
              {DIFFICULTY_LEVELS.map((level) => (
                <span
                  key={level.value}
                  className="text-[12px] text-[var(--text-secondary)]"
                >
                  {level.label}
                </span>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              Generated cases are distributed evenly across difficulty levels.
            </p>
          </div>

          <div>
            <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
              Additional Instructions <span className="text-[var(--text-muted)] font-normal">(optional)</span>
            </label>
            <textarea
              value={extraInstructions}
              onChange={(e) => onExtraInstructionsChange(e.target.value)}
              placeholder="e.g. Focus on Hindi food items, exercise correction flows, or stubborn users."
              rows={3}
              className="w-full rounded-[6px] border border-[var(--border-input)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--interactive-primary)] resize-y"
            />
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              These instructions are appended to the generation prompt for this run only.
            </p>
          </div>
        </Card>
      )}

      {libraryEnabled && (
        <Card className="space-y-4" hoverable={false}>
          <SectionHeader
            title="Saved Case Library"
            description="Select known regression cases, include pinned cases automatically, or curate the library as you build the run."
          />

          <div className="flex flex-col gap-3 rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3 md:flex-row md:items-center md:justify-between">
            <div className="grid gap-2 md:grid-cols-3 md:gap-3">
              <SummaryPill label="Selected Cases" value={selectedSavedCount} />
              <SummaryPill label="Pinned Auto-Include" value={includePinnedCases ? 'On' : 'Off'} />
              <SummaryPill label="Library Total" value={savedCases.length} />
            </div>
            <Button
              variant="secondary"
              icon={Library}
              onClick={() => setLibraryOverlayOpen(true)}
            >
              Manage Saved Cases
            </Button>
          </div>

          {(selectedSavedCases.length > 0 || includePinnedCases) && (
            <div className="rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
              <div className="flex items-center gap-2 mb-2">
                <Library className="h-4 w-4 text-[var(--text-brand)]" />
                <p className="text-[12px] font-semibold text-[var(--text-primary)]">
                  This Run Includes
                </p>
              </div>
              <div className="space-y-2">
                {selectedSavedCases.map((testCase) => (
                  <div
                    key={testCase.id}
                    className="flex items-center justify-between gap-3 rounded-[6px] bg-[var(--bg-primary)] px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="text-[12px] font-medium text-[var(--text-primary)] truncate">
                        {testCase.name || truncateText(testCase.syntheticInput, 72)}
                      </p>
                      <p className="text-[11px] text-[var(--text-muted)] truncate">
                        {(testCase.goalFlow || []).map(humanize).join(' → ')}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => toggleSavedCaseSelection(testCase.id)}
                      className="text-[11px] text-[var(--text-brand)] hover:underline"
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {includePinnedCases && pinnedAvailableCount > 0 && (
                  <p className="text-[11px] text-[var(--text-muted)]">
                    All pinned cases will also be added automatically.
                  </p>
                )}
              </div>
            </div>
          )}
        </Card>
      )}

      <Card className="space-y-4" hoverable={false}>
        <SectionHeader
          title="Manual Case Builder"
          description="Write a regression case once, then either include it only for this run or save it to the library for reuse."
        />

        <div className="flex flex-col gap-3 rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3 md:flex-row md:items-center md:justify-between">
          <div className="grid gap-2 md:grid-cols-2 md:gap-3">
            <SummaryPill label="Run-Only Cases" value={manualCases.length} />
            <SummaryPill label="Draft Status" value={manualDraftIsDirty ? 'In Progress' : 'Empty'} />
          </div>
          <Button
            variant="secondary"
            icon={Plus}
            onClick={() => setManualCaseOverlayOpen(true)}
          >
            Create Manual Case
          </Button>
        </div>

        {manualCases.length > 0 && (
          <div className="rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3 space-y-2">
            <p className="text-[12px] font-semibold text-[var(--text-primary)]">
              Run-Only Manual Cases
            </p>
            {manualCases.map((testCase, index) => (
              <div
                key={`${manualCaseKey(testCase)}-${index}`}
                className="flex items-center justify-between gap-3 rounded-[6px] bg-[var(--bg-primary)] px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-[12px] font-medium text-[var(--text-primary)] truncate">
                    {testCase.name || truncateText(testCase.syntheticInput, 72)}
                  </p>
                  <p className="text-[11px] text-[var(--text-muted)] truncate">
                    {(testCase.goalFlow || []).map(humanize).join(' → ')}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => removeManualCase(index)}
                  className="text-[11px] text-[var(--text-brand)] hover:underline"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <div>
        <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
          Turn Delay
        </label>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={0.5}
            max={5}
            step={0.5}
            value={turnDelay}
            onChange={(e) => onTurnDelayChange(parseFloat(e.target.value))}
            className="flex-1"
          />
          <span className="w-12 text-right text-[12px] text-[var(--text-secondary)]">
            {turnDelay.toFixed(1)}s
          </span>
        </div>
        <p className="mt-1 text-[11px] text-[var(--text-muted)]">
          Delay between user turns to avoid hammering the Kaira API.
        </p>
      </div>

      <div>
        <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
          Case Delay
        </label>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={0}
            max={10}
            step={0.5}
            value={caseDelay}
            onChange={(e) => onCaseDelayChange(parseFloat(e.target.value))}
            className="flex-1"
          />
          <span className="w-12 text-right text-[12px] text-[var(--text-secondary)]">
            {caseDelay.toFixed(1)}s
          </span>
        </div>
        <p className="mt-1 text-[11px] text-[var(--text-muted)]">
          Delay between starting test cases. Useful when the bot has strict rate limits.
        </p>
      </div>

      <SettingsSlideOver
        isOpen={libraryOverlayOpen}
        onClose={() => setLibraryOverlayOpen(false)}
        title="Saved Case Library"
        description="Search, filter, pin, and select reusable regression cases for this run."
        widthClassName="w-[62vw] max-w-[960px]"
        footerContent={(
          <div className="text-[12px] text-[var(--text-muted)]">
            Selection updates this run immediately. Close when the set looks right.
          </div>
        )}
      >
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <SummaryPill label="Selected Cases" value={selectedSavedCount} />
            <SummaryPill label="Pinned Auto-Include" value={includePinnedCases ? 'On' : 'Off'} />
            <SummaryPill label="Visible Results" value={filteredLibraryCases.length} />
          </div>

          <div className="flex flex-col gap-3 md:flex-row md:items-end">
            <div className="flex-1">
              <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
                Search Saved Cases
              </label>
              <Input
                value={librarySearch}
                onChange={(e) => setLibrarySearch(e.target.value)}
                placeholder="Search by title, opening message, goal, or trait..."
              />
            </div>
            <label className="inline-flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={onlyPinnedLibrary}
                onChange={(e) => setOnlyPinnedLibrary(e.target.checked)}
              />
              Show only pinned
            </label>
            <label className="inline-flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={includePinnedCases}
                onChange={(e) => onIncludePinnedCasesChange(e.target.checked)}
              />
              Include all pinned cases in this run
            </label>
          </div>

          <div className="rounded-[6px] border border-[var(--border-subtle)] overflow-hidden">
            <div className="max-h-[480px] overflow-y-auto divide-y divide-[var(--border-subtle)] bg-[var(--bg-secondary)]">
              {loading ? (
                <div className="p-3">
                  <LoadingRow label="Loading saved cases..." />
                </div>
              ) : filteredLibraryCases.length === 0 ? (
                <div className="p-4 text-[12px] text-[var(--text-muted)]">
                  No saved cases match the current filters.
                </div>
              ) : (
                filteredLibraryCases.map((testCase) => {
                  const selected = selectedSavedCaseIds.includes(testCase.id);
                  return (
                    <div
                      key={testCase.id}
                      className={`flex items-start gap-3 px-3 py-3 ${selected ? 'bg-[var(--bg-primary)]' : ''}`}
                    >
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleSavedCaseSelection(testCase.id)}
                        className="mt-1"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-[12px] font-semibold text-[var(--text-primary)] truncate">
                            {testCase.name || truncateText(testCase.syntheticInput, 72)}
                          </p>
                          {testCase.isPinned && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-primary)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-brand)]">
                              <Pin className="h-3 w-3" />
                              Pinned
                            </span>
                          )}
                          <span className="inline-flex rounded-full bg-[var(--bg-primary)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-muted)]">
                            {testCase.difficulty}
                          </span>
                        </div>
                        <p className="mt-1 text-[12px] leading-relaxed text-[var(--text-secondary)]">
                          {truncateText(testCase.syntheticInput, 140)}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {testCase.goalFlow.map((goalId) => (
                            <span
                              key={`${testCase.id}-goal-${goalId}`}
                              className="rounded-full bg-[var(--bg-primary)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]"
                            >
                              {humanize(goalId)}
                            </span>
                          ))}
                          {testCase.activeTraits.map((traitId) => (
                            <span
                              key={`${testCase.id}-trait-${traitId}`}
                              className="rounded-full bg-[var(--bg-primary)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)]"
                            >
                              {humanize(traitId)}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          type="button"
                          onClick={() => toggleCasePinned(testCase)}
                          disabled={libraryBusyId === testCase.id}
                          className="rounded-md p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)]"
                          title={testCase.isPinned ? 'Unpin case' : 'Pin case'}
                        >
                          {testCase.isPinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteSavedCase(testCase)}
                          disabled={libraryBusyId === testCase.id}
                          className="rounded-md p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-primary)] hover:text-[var(--color-error)]"
                          title="Delete saved case"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </SettingsSlideOver>

      <SettingsSlideOver
        isOpen={manualCaseOverlayOpen}
        onClose={() => setManualCaseOverlayOpen(false)}
        title="Create Manual Case"
        description="Add a run-only regression case or save it into the reusable library."
        widthClassName="w-[56vw] max-w-[880px]"
        isDirty={manualDraftIsDirty}
        footerContent={(
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={saveDraftPinned}
                onChange={(e) => setSaveDraftPinned(e.target.checked)}
              />
              Pin when saving to library
            </label>
            <Button
              variant="secondary"
              icon={Save}
              onClick={() => {
                void saveDraftToLibrary();
              }}
              disabled={!canAddDraftToRun || savingDraft}
              isLoading={savingDraft}
            >
              Save To Library
            </Button>
          </div>
        )}
        onSubmit={addDraftToRun}
        submitLabel="Add To Run"
        canSubmit={canAddDraftToRun && !savingDraft}
      >
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
                Case Name <span className="text-[var(--text-muted)] font-normal">(optional)</span>
              </label>
              <Input
                value={draft.name || ''}
                onChange={(e) => setDraft((current) => ({ ...current, name: e.target.value }))}
                placeholder="e.g. Future meal should be rejected"
              />
            </div>
            <div>
              <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
                Difficulty
              </label>
              <div className="flex gap-2">
                {DIFFICULTY_LEVELS.map((level) => (
                  <button
                    key={level.value}
                    type="button"
                    onClick={() => setDraft((current) => ({ ...current, difficulty: level.value }))}
                    className={`px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors ${
                      draft.difficulty === level.value
                        ? 'bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)] ring-1 ring-[var(--color-brand-accent)]/40'
                        : 'bg-[var(--bg-secondary)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                    }`}
                  >
                    {level.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div>
            <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
              Opening Message
            </label>
            <textarea
              value={draft.syntheticInput}
              onChange={(e) => setDraft((current) => ({ ...current, syntheticInput: e.target.value }))}
              placeholder="The first message the simulated user sends to Kaira."
              rows={3}
              className="w-full rounded-[6px] border border-[var(--border-input)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--interactive-primary)] resize-y"
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
                Goal Flow
              </label>
              {loading ? (
                <LoadingRow label="Loading goals..." />
              ) : (
                <MultiSelect
                  values={draft.goalFlow}
                  onChange={(values) => setDraft((current) => ({ ...current, goalFlow: values }))}
                  options={goalOptions}
                  placeholder="Select goals"
                />
              )}
            </div>

            <div>
              <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
                Active Traits
              </label>
              {loading ? (
                <LoadingRow label="Loading traits..." />
              ) : (
                <MultiSelect
                  values={draft.activeTraits}
                  onChange={(values) => setDraft((current) => ({ ...current, activeTraits: values }))}
                  options={traitOptions}
                  placeholder="Select traits"
                />
              )}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
                Description <span className="text-[var(--text-muted)] font-normal">(optional)</span>
              </label>
              <textarea
                value={draft.description || ''}
                onChange={(e) => setDraft((current) => ({ ...current, description: e.target.value }))}
                placeholder="Explain what regression or edge case this protects."
                rows={3}
                className="w-full rounded-[6px] border border-[var(--border-input)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--interactive-primary)] resize-y"
              />
            </div>
            <div>
              <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
                Expected Challenges <span className="text-[var(--text-muted)] font-normal">(one per line)</span>
              </label>
              <textarea
                value={draftChallengesText}
                onChange={(e) => setDraftChallengesText(e.target.value)}
                placeholder={'Bot should reject future time\nBot should ask a follow-up instead of guessing'}
                rows={3}
                className="w-full rounded-[6px] border border-[var(--border-input)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--interactive-primary)] resize-y"
              />
            </div>
          </div>
        </div>
      </SettingsSlideOver>
    </div>
  );
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex items-start gap-2">
      <Info className="mt-0.5 h-4 w-4 text-[var(--text-muted)]" />
      <div>
        <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">{title}</h3>
        <p className="text-[11px] leading-relaxed text-[var(--text-muted)]">{description}</p>
      </div>
    </div>
  );
}

function SummaryPill({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] font-semibold">
        {label}
      </p>
      <p className="mt-0.5 text-[16px] font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--text-muted)]" />
      <span className="text-[11px] text-[var(--text-muted)]">{label}</span>
    </div>
  );
}

function truncateText(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}…`;
}
