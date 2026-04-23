/**
 * Page action slot registry.
 *
 * Maps `apps.config.pageActions[pageType][i].kind` strings to the React
 * component that renders the action. Shared page components consume this via
 * `useAppPageActions(pageType)` and pass the result to `PageSurface.actions`.
 *
 * Phase 0 lands the plumbing with four placeholder kinds. Phase 1 replaces
 * the placeholder bodies with the real extracted components (e.g. the CSV
 * import action lifted out of `InsideSalesEvaluators.tsx`).
 */
import type { ComponentType, ReactElement } from 'react';
import { useMemo } from 'react';

import { PermissionGate } from '@/components/auth/PermissionGate';
import { useCurrentAppConfig } from '@/hooks';
import type { PageActionSpec, PageType } from '@/types';

import { CsvImportAction } from '@/features/evals/components/actions/CsvImportAction';
import { ExportAction } from './components/ExportAction';
import { FreshnessBadgeAction } from './components/FreshnessBadgeAction';
import { RefreshAction } from './components/RefreshAction';

export interface PageActionComponentProps {
  config?: Record<string, unknown>;
  displayMode?: 'button' | 'icon';
}

interface UseAppPageActionsOptions {
  displayMode?: 'button' | 'icon';
}

export const PAGE_ACTION_COMPONENTS: Record<string, ComponentType<PageActionComponentProps>> = {
  csvImport: CsvImportAction,
  freshnessBadge: FreshnessBadgeAction,
  refresh: RefreshAction,
  export: ExportAction,
};

export function useAppPageActions(
  pageType: PageType,
  options: UseAppPageActionsOptions = {},
): ReactElement[] {
  const appConfig = useCurrentAppConfig();
  const specs = appConfig.pageActions?.[pageType];
  const { displayMode = 'button' } = options;

  return useMemo(() => {
    if (!specs || specs.length === 0) return [];
    return specs
      .map((spec) => renderPageAction(spec, displayMode))
      .filter((node): node is ReactElement => node !== null);
  }, [displayMode, specs]);
}

function renderPageAction(
  spec: PageActionSpec,
  displayMode: 'button' | 'icon',
): ReactElement | null {
  const Component = PAGE_ACTION_COMPONENTS[spec.kind];
  if (!Component) return null;

  const node = <Component key={spec.id} config={spec.config} displayMode={displayMode} />;
  if (spec.requires) {
    return (
      <PermissionGate key={spec.id} action={spec.requires}>
        {node}
      </PermissionGate>
    );
  }
  return node;
}
