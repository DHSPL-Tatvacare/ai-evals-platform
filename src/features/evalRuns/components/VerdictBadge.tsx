import { useRef, useState } from "react";
import {
  getLabelDefinition,
  type LabelCategory,
  EFFICIENCY_VERDICTS,
  DIFFICULTY_LEVELS,
  RUN_STATUS_LABELS,
} from "@/config/labelDefinitions";
import { normalizeLabel } from "@/utils/evalFormatters";
import Tooltip from "./Tooltip";
import { VerdictChip } from '@/features/reviews/inline';

interface Props {
  verdict: string;
  category?: LabelCategory;
  size?: "sm" | "md";
  showTooltip?: boolean;
  humanVerdict?: string;
}

const EFFICIENCY_SET = new Set(Object.keys(EFFICIENCY_VERDICTS));
const DIFFICULTY_SET = new Set(Object.keys(DIFFICULTY_LEVELS));
const STATUS_SET = new Set(Object.keys(RUN_STATUS_LABELS));

function detectCategory(verdict: string): LabelCategory {
  const n = normalizeLabel(verdict);
  if (EFFICIENCY_SET.has(n)) return "efficiency";
  if (DIFFICULTY_SET.has(n)) return "difficulty";
  if (STATUS_SET.has(n)) return "status";
  return "correctness";
}

// Single source of truth for "AI vs human" dispatch lives in VerdictChip.
// VerdictBadge wraps it and adds the hover tooltip that non-review callers
// want on the plain AI badge.
export default function VerdictBadge({
  verdict,
  category,
  size = "sm",
  showTooltip = true,
  humanVerdict,
}: Props) {
  const resolved = category ?? detectCategory(verdict);
  return (
    <VerdictChip
      aiVerdict={verdict}
      humanVerdict={humanVerdict}
      category={resolved}
      size={size}
      renderBadge={(value) => (
        <PlainBadge value={value ?? ''} category={resolved} size={size} showTooltip={showTooltip} />
      )}
    />
  );
}

function PlainBadge({
  value,
  category,
  size,
  showTooltip,
}: {
  value: string;
  category: LabelCategory;
  size: "sm" | "md";
  showTooltip: boolean;
}) {
  const [hover, setHover] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const def = getLabelDefinition(value, category);

  const cls =
    size === "sm"
      ? "px-1.5 py-px text-[10px]"
      : "px-2 py-0.5 text-xs";

  return (
    <span className="inline-block">
      <span
        ref={ref}
        className={`inline-block rounded-full font-semibold text-[var(--text-on-color)] tracking-wide leading-snug cursor-help transition-opacity hover:opacity-90 ${cls}`}
        style={{ backgroundColor: def.color }}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        {def.displayName}
      </span>
      {showTooltip && (
        <Tooltip
          title={def.displayName}
          body={def.tooltip}
          visible={hover}
          anchorRef={ref}
        />
      )}
    </span>
  );
}
