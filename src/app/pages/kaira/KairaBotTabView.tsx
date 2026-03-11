/**
 * Kaira Bot Tab View
 * Main view with Chat and Trace Analysis tabs (similar to Voice Rx pattern)
 */

import { useSearchParams, useParams, useNavigate } from "react-router-dom";
import { useCallback, useEffect } from "react";
import { Spinner, Tabs } from "@/components/ui";
import { ChatView } from "@/features/kaira/components/ChatView";
import { TraceAnalysisView } from "@/features/kaira/components";
import { KairaBotEvaluatorsView } from "@/features/kaira/components/KairaBotEvaluatorsView";
import { useKairaChat } from "@/hooks";
import { routes } from "@/config/routes";

export function KairaBotTabView() {
  const [searchParams] = useSearchParams();
  const { chatId: chatIdFromUrl } = useParams<{ chatId?: string }>();
  const navigate = useNavigate();

  const {
    currentSession,
    messages,
    isSessionsLoaded,
    isLoadingSessions,
    isLoadingMessages,
    sessions,
    selectSession,
  } = useKairaChat({ chatIdHint: chatIdFromUrl });

  // Get active tab from URL or default to 'chat'
  const activeTab = searchParams.get("tab") || "chat";

  const handleTabChange = useCallback(
    (tabId: string) => {
      if (currentSession) {
        navigate(`${routes.kaira.chatSession(currentSession.id)}?tab=${tabId}`);
      } else {
        navigate(`${routes.kaira.chat}?tab=${tabId}`);
      }
    },
    [currentSession, navigate],
  );

  // Sync URL when the selected session changes.
  // - replace (no back-history entry) on initial auto-select (no chatId in URL yet)
  // - push (back-history entry) on explicit session switch (chatId already in URL but different)
  useEffect(() => {
    if (currentSession && currentSession.id !== chatIdFromUrl) {
      const tab = searchParams.get("tab") || "chat";
      navigate(`${routes.kaira.chatSession(currentSession.id)}?tab=${tab}`, {
        replace: !chatIdFromUrl,
      });
    }
    // Session was deleted (currentSession is null but URL still has a chatId) —
    // navigate back to base chat URL so the next session can be auto-selected.
    if (
      !currentSession &&
      chatIdFromUrl &&
      isSessionsLoaded &&
      !isLoadingSessions
    ) {
      const tab = searchParams.get("tab") || "chat";
      if (sessions.length > 0) {
        // Auto-select the first remaining session
        const nextId = sessions[0].id;
        navigate(`${routes.kaira.chatSession(nextId)}?tab=${tab}`, {
          replace: true,
        });
      } else {
        navigate(`${routes.kaira.chat}?tab=${tab}`, { replace: true });
      }
    }
  }, [
    currentSession,
    chatIdFromUrl,
    searchParams,
    navigate,
    isSessionsLoaded,
    isLoadingSessions,
    sessions,
  ]);

  // When the URL chatId changes (e.g. sidebar click navigates), select that session in the store
  useEffect(() => {
    if (
      chatIdFromUrl &&
      isSessionsLoaded &&
      !isLoadingSessions &&
      currentSession?.id !== chatIdFromUrl &&
      sessions.some((s) => s.id === chatIdFromUrl)
    ) {
      selectSession(chatIdFromUrl);
    }
  }, [
    chatIdFromUrl,
    isSessionsLoaded,
    isLoadingSessions,
    currentSession?.id,
    sessions,
    selectSession,
  ]);

  // Settled = sessions fetched + a session selected + its messages loaded.
  // sessions.length === 0 covers new users: no session will ever be selected,
  // so don't wait for one — let the tabs render (ChatView will auto-create).
  const isReady =
    isSessionsLoaded &&
    !isLoadingSessions &&
    !isLoadingMessages &&
    (sessions.length === 0 || currentSession !== null);

  if (!isReady) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-center flex-1">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  const tabs = [
    {
      id: "chat",
      label: "Chat",
      content: <ChatView />,
    },
    {
      id: "traces",
      label: "Traces",
      content: (
        <TraceAnalysisView session={currentSession} messages={messages} />
      ),
    },
    {
      id: "evaluators",
      label: "Evaluators",
      content: (
        <KairaBotEvaluatorsView session={currentSession} messages={messages} />
      ),
    },
  ];

  return (
    <div className="flex flex-col h-full">
      <Tabs
        tabs={tabs}
        defaultTab={activeTab}
        onChange={handleTabChange}
        fillHeight
      />
    </div>
  );
}
