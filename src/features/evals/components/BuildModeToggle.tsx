import { cn } from '@/utils';

export type EvaluatorBuildMode = 'prompt' | 'rubric';

interface BuildModeToggleProps {
  value: EvaluatorBuildMode;
  onChange: (value: EvaluatorBuildMode) => void;
  allowRubric: boolean;
}

export function BuildModeToggle({ value, onChange, allowRubric }: BuildModeToggleProps) {
  const options: EvaluatorBuildMode[] = allowRubric ? ['prompt', 'rubric'] : ['prompt'];

  return (
    <div className="inline-flex rounded-[8px] border border-[var(--border-default)] bg-[var(--bg-secondary)] p-1">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          className={cn(
            'rounded-[6px] px-3 py-1.5 text-[12px] font-medium transition-colors',
            value === option
              ? 'bg-[var(--interactive-primary)] text-[var(--text-on-color)]'
              : 'text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]',
          )}
        >
          {option === 'prompt' ? 'Write Prompt' : 'Use Rubric'}
        </button>
      ))}
    </div>
  );
}
