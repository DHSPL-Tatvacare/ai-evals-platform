import { getLabelDefinition } from '@/config/labelDefinitions';
import type { CorrectnessVerdict } from '@/types/evalRuns';
import type { EvalTab } from './useEvalLinking';

interface Props {
  turnIndex: number;
  correctnessVerdict?: CorrectnessVerdict;
  isCorrectIntent?: boolean;
  onBadgeClick: (turnIndex: number, evalType: EvalTab) => void;
}

export default function ChatTurnBadges({
  turnIndex,
  correctnessVerdict,
  isCorrectIntent,
  onBadgeClick,
}: Props) {
  const hasAnything = correctnessVerdict || isCorrectIntent != null;
  if (!hasAnything) return null;

  return (
    <span className="inline-flex items-center gap-2 ml-auto">
      {correctnessVerdict && (
        <AnnotationChip
          color={getLabelDefinition(correctnessVerdict, 'correctness').color}
          label={getLabelDefinition(correctnessVerdict, 'correctness').displayName}
          onClick={() => onBadgeClick(turnIndex, 'correctness')}
          title="View correctness evaluation"
        />
      )}

      {isCorrectIntent != null && (
        <AnnotationChip
          color={isCorrectIntent ? 'var(--color-success)' : 'var(--color-error)'}
          label={isCorrectIntent ? 'Judge OK' : 'Judge Miss'}
          onClick={() => onBadgeClick(turnIndex, 'intent')}
          title={isCorrectIntent ? 'Judge intent matched' : 'Judge intent mismatch'}
        />
      )}
    </span>
  );
}

function AnnotationChip({
  color,
  label,
  onClick,
  title,
}: {
  color: string;
  label: string;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      className="inline-flex items-center gap-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors cursor-pointer focus-visible:outline-none"
      title={title}
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
        style={{ backgroundColor: color }}
      />
      {label}
    </button>
  );
}
