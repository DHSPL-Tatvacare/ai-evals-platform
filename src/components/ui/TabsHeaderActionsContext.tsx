import { createContext, type ReactNode, useContext, useEffect } from 'react';

export interface TabsHeaderActionsContextValue {
  setHeaderActions: (tabId: string, actions: ReactNode | null) => void;
}

export const TabsHeaderActionsContext = createContext<TabsHeaderActionsContextValue | null>(null);

export function useTabsHeaderActions(tabId: string, actions: ReactNode | null): void {
  const context = useContext(TabsHeaderActionsContext);

  useEffect(() => {
    if (!context) {
      return;
    }

    context.setHeaderActions(tabId, actions);
    return () => {
      context.setHeaderActions(tabId, null);
    };
  }, [actions, context, tabId]);
}
