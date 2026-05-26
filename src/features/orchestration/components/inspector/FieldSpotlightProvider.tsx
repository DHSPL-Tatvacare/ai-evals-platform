import { useCallback, useEffect, useMemo, type ReactNode } from 'react';

import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';

import {
  FieldSpotlightContext,
  indexFieldNodeIds,
  type FieldNodeRef,
  type FieldSpotlightValue,
} from './fieldSpotlight';

/** Provides hover->spotlight wiring for every upstream-field picker rendered
 *  inside it. Lives once per inspector body; holds the `path -> nodeId` index
 *  and drives `workflowBuilderStore.setSpotlightNode`. Clears the spotlight on
 *  unmount so closing or switching the inspector never strands a dimmed
 *  canvas. */
export function FieldSpotlightProvider({
  fields,
  children,
}: {
  fields: readonly FieldNodeRef[];
  children: ReactNode;
}) {
  const setSpotlightNode = useWorkflowBuilderStore((s) => s.setSpotlightNode);
  const index = useMemo(() => indexFieldNodeIds(fields), [fields]);

  const enter = useCallback(
    (path: string) => setSpotlightNode(index.get(path) ?? null),
    [index, setSpotlightNode],
  );
  const leave = useCallback(() => setSpotlightNode(null), [setSpotlightNode]);

  useEffect(() => () => setSpotlightNode(null), [setSpotlightNode]);

  const value = useMemo<FieldSpotlightValue>(
    () => ({ enter, leave }),
    [enter, leave],
  );

  return (
    <FieldSpotlightContext.Provider value={value}>
      {children}
    </FieldSpotlightContext.Provider>
  );
}
