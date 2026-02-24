import { useReducer, useEffect, useCallback, useRef } from 'react';

export type EvalTab = 'efficiency' | 'correctness' | 'intent' | 'custom' | 'rules';

interface LinkingState {
  activeTab: EvalTab;
  activeTurnIndex: number | null;
  source: 'chat' | 'table' | null;
}

type LinkingAction =
  | { type: 'CHAT_CLICK'; turnIndex: number; evalType: EvalTab }
  | { type: 'TABLE_HOVER'; turnIndex: number | null }
  | { type: 'TAB_CHANGE'; tab: EvalTab }
  | { type: 'CLEAR' };

function reducer(state: LinkingState, action: LinkingAction): LinkingState {
  switch (action.type) {
    case 'CHAT_CLICK':
      return {
        activeTab: action.evalType,
        activeTurnIndex: action.turnIndex,
        source: 'chat',
      };
    case 'TABLE_HOVER':
      return {
        ...state,
        activeTurnIndex: action.turnIndex,
        source: action.turnIndex != null ? 'table' : null,
      };
    case 'TAB_CHANGE':
      return { activeTab: action.tab, activeTurnIndex: null, source: null };
    case 'CLEAR':
      return { ...state, activeTurnIndex: null, source: null };
    default:
      return state;
  }
}

export function useEvalLinking(defaultTab: EvalTab = 'efficiency') {
  const [state, dispatch] = useReducer(reducer, {
    activeTab: defaultTab,
    activeTurnIndex: null,
    source: null,
  });

  const clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-clear highlight after 2.5s
  useEffect(() => {
    if (state.activeTurnIndex != null) {
      if (clearTimerRef.current) clearTimeout(clearTimerRef.current);
      clearTimerRef.current = setTimeout(() => dispatch({ type: 'CLEAR' }), 2500);
    }
    return () => {
      if (clearTimerRef.current) clearTimeout(clearTimerRef.current);
    };
  }, [state.activeTurnIndex]);

  const onChatClick = useCallback((turnIndex: number, evalType: EvalTab) => {
    dispatch({ type: 'CHAT_CLICK', turnIndex, evalType });
    // Scroll table row into view
    const el = document.getElementById(`eval-row-${evalType}-${turnIndex}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, []);

  const onTableHover = useCallback((turnIndex: number | null) => {
    dispatch({ type: 'TABLE_HOVER', turnIndex });
    if (turnIndex != null) {
      const el = document.getElementById(`thread-turn-${turnIndex}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, []);

  const onTabChange = useCallback((tab: EvalTab) => {
    dispatch({ type: 'TAB_CHANGE', tab });
  }, []);

  return {
    activeTab: state.activeTab,
    activeTurnIndex: state.activeTurnIndex,
    source: state.source,
    onChatClick,
    onTableHover,
    onTabChange,
  };
}
