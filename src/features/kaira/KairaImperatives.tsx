/**
 * Registers kaira-owned imperative triggers into uiStore so generic
 * data-driven quick-action specs (`triggerImperative` kind) can invoke them
 * without the registry / sidebar knowing what they do.
 *
 * Mount this near the top of the tree (MainLayout) — does not render. The
 * trigger stays registered for the lifetime of the session so the sidebar's
 * "Run" menu can fire it from any route, not only when a kaira page is open.
 */
import { useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import { routes } from '@/config/routes';
import { useAppStore, useChatStore, useKairaBotSettings, useUIStore } from '@/stores';

const TRIGGER_KEY = 'kaira.createSession';

export function KairaImperatives() {
  const navigate = useNavigate();
  const appId = useAppStore((s) => s.currentApp);
  const { settings: kairaBotSettings } = useKairaBotSettings();
  const userId = kairaBotSettings.kairaChatUserId;
  const createSession = useChatStore((s) => s.createSession);
  const isCreating = useChatStore((s) => s.isCreatingSession);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const registerTrigger = useUIStore((s) => s.registerTrigger);

  const trigger = useCallback(async () => {
    if (!userId || isCreating || isStreaming) return;
    try {
      const session = await createSession(appId, userId);
      navigate(routes.kaira.chatSession(session.id));
    } catch (err) {
      console.warn('kaira.createSession trigger skipped:', err);
    }
  }, [appId, createSession, isCreating, isStreaming, navigate, userId]);

  useEffect(() => registerTrigger(TRIGGER_KEY, trigger), [registerTrigger, trigger]);
  return null;
}
