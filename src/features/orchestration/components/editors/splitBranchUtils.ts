import type {
  SplitBranch,
  SplitMode,
} from '@/features/orchestration/types';

interface SplitConfig {
  mode?: SplitMode;
  field?: string;
  branches?: SplitBranch[];
  default_branch_id?: string;
  drop_unmatched?: boolean;
  holdout_percent?: number;
}

function normalizeBranchForMode(branch: SplitBranch, mode: SplitMode): SplitBranch {
  const base: SplitBranch = {
    id: branch.id,
    label: branch.label,
  };
  if (mode === 'by_field') {
    return {
      ...base,
      match:
        typeof branch.match === 'string'
          ? branch.match
          : branch.match === undefined || branch.match === null
            ? ''
            : String(branch.match),
    };
  }
  if (mode === 'random') {
    return {
      ...base,
      weight: typeof branch.weight === 'number' ? branch.weight : 1,
    };
  }
  // percentage
  return {
    ...base,
    percent: typeof branch.percent === 'number' ? branch.percent : 0,
  };
}

export function normalizeSplitConfigForMode(
  value: SplitConfig,
  nextMode: SplitMode,
): SplitConfig {
  const normalizedBranches = (value.branches ?? []).map((branch) =>
    normalizeBranchForMode(branch, nextMode),
  );
  const nextConfig: SplitConfig = {
    ...value,
    mode: nextMode,
    branches: normalizedBranches,
    default_branch_id: normalizedBranches.some(
      (branch) => branch.id === value.default_branch_id,
    )
      ? value.default_branch_id
      : undefined,
  };
  if (nextMode === 'by_field') {
    nextConfig.field = value.field ?? '';
  } else {
    delete nextConfig.field;
  }
  if (nextMode !== 'percentage') {
    delete nextConfig.holdout_percent;
  }
  return nextConfig;
}
