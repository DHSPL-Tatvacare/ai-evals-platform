/**
 * Quick-action registry types.
 *
 * The runtime type a kind handler returns. Kinds are generic primitives
 * (`openModal` / `triggerImperative` / `navigateTo`); app-specific behavior
 * lives in the spec's `config` payload and in feature modules that register
 * imperative triggers — never as new kinds.
 */
import type { LucideIcon } from 'lucide-react';
import type { QuickActionSpec } from '@/types';
import type { ActionAvailabilityBlocker } from '@/utils/actionAvailability';

export interface QuickActionItem {
  /** `QuickActionSpec.id` — stable per-app instance identifier. */
  id: string;
  /** Registry kind. */
  kind: string;
  label: string;
  description: string;
  icon: LucideIcon;
  onSelect: () => void;
  disabled: boolean;
  isLoading: boolean;
  blockers: ActionAvailabilityBlocker[];
}

export type QuickActionRuntime = Pick<
  QuickActionItem,
  'onSelect' | 'disabled' | 'isLoading' | 'blockers'
>;

export interface QuickActionDescriptor {
  /** Hook called inside an isolated child component — exactly one per spec.
   *  Receives the full spec so the kind handler can read `spec.config` for
   *  per-instance parameters and `spec.requirements` for per-spec gates. */
  useResolve: (spec: QuickActionSpec) => QuickActionRuntime;
}
