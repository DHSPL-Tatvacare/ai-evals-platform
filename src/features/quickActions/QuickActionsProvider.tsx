/**
 * <QuickActionsProvider> — render-prop wrapper that yields the resolved list
 * of QuickActionItems for the current app + viewer.
 *
 * Hook safety: each spec is resolved inside its own `<ResolveOne>` mount, so
 * the hook count per child is always exactly one. Reordering, adding, or
 * removing specs in the parent stays React-legal because each child has its
 * own hook stack and the keyed list teardown unmounts gone ones.
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { useCurrentAppConfig } from '@/hooks';
import { useAuthStore } from '@/stores/authStore';
import type { PageActionSpec } from '@/types';
import { userHasPermission } from '@/utils/permissions';

import { QUICK_ACTION_REGISTRY } from './registry';
import type { QuickActionDescriptor, QuickActionItem } from './types';

/** Specs filtered for the current viewer. Pure data — no descriptor hooks
 *  called here. Unknown kinds and permission-denied items are dropped. */
function useResolvedQuickActionSpecs(): Array<{
  spec: PageActionSpec;
  descriptor: QuickActionDescriptor;
}> {
  const appConfig = useCurrentAppConfig();
  const user = useAuthStore((s) => s.user);
  return useMemo(() => {
    const specs = appConfig.quickActions ?? [];
    const out: Array<{ spec: PageActionSpec; descriptor: QuickActionDescriptor }> = [];
    for (const spec of specs) {
      const descriptor = QUICK_ACTION_REGISTRY[spec.kind];
      if (!descriptor) continue;
      if (spec.requires && !userHasPermission(user, spec.requires)) continue;
      out.push({ spec, descriptor });
    }
    return out;
  }, [appConfig.quickActions, user]);
}

function ResolveOne({
  spec,
  descriptor,
  onResolved,
}: {
  spec: PageActionSpec;
  descriptor: QuickActionDescriptor;
  onResolved: (item: QuickActionItem) => void;
}) {
  const runtime = descriptor.useResolve(spec);
  const onResolvedRef = useRef(onResolved);
  onResolvedRef.current = onResolved;
  // Listing the runtime fields explicitly (instead of `runtime`) is the
  // intent — we want to re-emit only when one of these primitives changes,
  // not on every parent render. The eslint-disable is precise to that.
  useEffect(() => {
    onResolvedRef.current({
      id: spec.id,
      kind: spec.kind,
      label: descriptor.label,
      description: descriptor.description,
      icon: descriptor.icon,
      ...runtime,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    spec.id,
    spec.kind,
    descriptor,
    runtime.onSelect,
    runtime.disabled,
    runtime.isLoading,
    runtime.blockers,
  ]);
  return null;
}

export function QuickActionsProvider({
  children,
}: {
  children: (items: QuickActionItem[]) => ReactNode;
}) {
  const resolved = useResolvedQuickActionSpecs();
  const [items, setItems] = useState<Record<string, QuickActionItem>>({});

  const handleResolved = useCallback((item: QuickActionItem) => {
    setItems((prev) => {
      const existing = prev[item.id];
      if (
        existing
        && existing.disabled === item.disabled
        && existing.isLoading === item.isLoading
        && existing.onSelect === item.onSelect
        && existing.blockers === item.blockers
      ) {
        return prev;
      }
      return { ...prev, [item.id]: item };
    });
  }, []);

  // Stale items (specs that disappeared on app switch) stay in the dict but
  // are filtered out at projection time. Memory cost is bounded by distinct
  // ids the session has ever seen — negligible. We intentionally avoid a
  // setState-in-effect cleanup pass.
  const orderedItems = useMemo(
    () => resolved.map(({ spec }) => items[spec.id]).filter((item): item is QuickActionItem => Boolean(item)),
    [resolved, items],
  );

  return (
    <>
      {resolved.map(({ spec, descriptor }) => (
        <ResolveOne key={spec.id} spec={spec} descriptor={descriptor} onResolved={handleResolved} />
      ))}
      <Fragment>{children(orderedItems)}</Fragment>
    </>
  );
}
