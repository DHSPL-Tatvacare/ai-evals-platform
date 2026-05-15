/**
 * Quick-action registry types — shared between the registry data module
 * and the `<QuickActionsProvider>` component. Lives in its own file so
 * react-refresh can hot-reload the provider component cleanly.
 */
import type { LucideIcon } from 'lucide-react';
import type { PageActionSpec } from '@/types';
import type { ActionAvailabilityBlocker } from '@/utils/actionAvailability';

export interface QuickActionItem {
  /** `PageActionSpec.id` — stable per-app instance identifier. */
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
  label: string;
  description: string;
  icon: LucideIcon;
  /** Hook called inside an isolated child component — exactly one per spec.
   *  Receives the spec so kinds can read `spec.config` for per-instance
   *  parameters (none today; reserved for the tenant-overlay phase). */
  useResolve: (spec: PageActionSpec) => QuickActionRuntime;
}
