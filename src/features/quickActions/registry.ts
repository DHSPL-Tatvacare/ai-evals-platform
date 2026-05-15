/**
 * Quick-action registry — kind → descriptor map.
 *
 * `kind` strings declared on `apps.config.quickActions[]` resolve to a
 * descriptor here. Each descriptor owns a `useResolve(spec)` hook that yields
 * the runtime piece of a `QuickActionItem` (onSelect, disabled, blockers,
 * isLoading). The sidebar stays a dumb renderer with no per-app branches.
 *
 * Adding a new action = register one entry here + emit the spec from the app
 * config (DB seed today, per-tenant overlay later — see
 * docs/plans/2026-05-15-tenant-account-setup-system/).
 */
import { useCallback } from 'react';
import {
  FileAudio,
  FileSpreadsheet,
  MessageSquare,
  ShieldAlert,
  Workflow,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { routes } from '@/config/routes';
import { useCurrentAppConfig } from '@/hooks';
import {
  useAppSettingsStore,
  useAppStore,
  useChatStore,
  useKairaBotSettings,
  useUIStore,
} from '@/stores';
import { evaluateActionAvailability } from '@/utils/actionAvailability';
import type { QuickActionDescriptor, QuickActionRuntime } from './types';

// ── Kind: kairaNewChat ───────────────────────────────────────────────────────
// Named after the action it actually performs (kaira-store createSession +
// nav to kaira.chatSession route). A generic "newChat" name would lie about
// the coupling and confuse the future tenant-overlay editor.
function useKairaNewChatRuntime(): QuickActionRuntime {
  const navigate = useNavigate();
  const appId = useAppStore((s) => s.currentApp);
  const appConfig = useCurrentAppConfig();
  const appSettings = useAppSettingsStore((s) => s.settings[appId]);
  const { settings: kairaBotSettings } = useKairaBotSettings();
  const kairaChatUserId = kairaBotSettings.kairaChatUserId;

  const isCreatingSession = useChatStore((s) => s.isCreatingSession);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const createSession = useChatStore((s) => s.createSession);

  const availability = evaluateActionAvailability({
    appId,
    action: appConfig.actions.primaryNew,
    sources: { appSettings },
    runtimeBlockers: [
      {
        key: 'action-in-progress',
        isActive: isCreatingSession || isStreaming,
        title: 'New Chat is temporarily unavailable',
        description: 'Wait for the current action to finish, then try again.',
      },
    ],
  });

  const onSelect = useCallback(async () => {
    if (!kairaChatUserId || isCreatingSession || isStreaming) return;
    try {
      const session = await createSession(appId, kairaChatUserId);
      navigate(routes.kaira.chatSession(session.id));
    } catch (err) {
      console.warn('Session creation skipped:', err);
    }
  }, [appId, createSession, isCreatingSession, isStreaming, kairaChatUserId, navigate]);

  return {
    onSelect,
    disabled: availability.disabled,
    isLoading: isCreatingSession,
    blockers: availability.blockers,
  };
}

// ── Kind: kairaBatchEval ─────────────────────────────────────────────────────
// Distinct kind per app-shape rather than a single `batchEval` that branches
// on app id — keeps the registry honest and lets future apps add their own
// batch flows without touching this file. Modal body is kaira-shaped.
function useKairaBatchEvalRuntime(): QuickActionRuntime {
  const openModal = useUIStore((s) => s.openModal);
  const onSelect = useCallback(() => openModal('batchEval'), [openModal]);
  return { onSelect, disabled: false, isLoading: false, blockers: [] };
}

// ── Kind: insideSalesBatchEval ───────────────────────────────────────────────
function useInsideSalesBatchEvalRuntime(): QuickActionRuntime {
  const openModal = useUIStore((s) => s.openModal);
  const onSelect = useCallback(() => openModal('insideSalesEval'), [openModal]);
  return { onSelect, disabled: false, isLoading: false, blockers: [] };
}

// ── Kind: adversarialTest ────────────────────────────────────────────────────
function useAdversarialTestRuntime(): QuickActionRuntime {
  const openModal = useUIStore((s) => s.openModal);
  const onSelect = useCallback(() => openModal('adversarialTest'), [openModal]);
  return { onSelect, disabled: false, isLoading: false, blockers: [] };
}

// ── Kind: voiceRxUpload ──────────────────────────────────────────────────────
function useVoiceRxUploadRuntime(): QuickActionRuntime {
  const invokeTrigger = useUIStore((s) => s.invokeTrigger);
  const hasTrigger = useUIStore((s) => Boolean(s.imperativeTriggers['voiceRxUpload']));
  const onSelect = useCallback(() => invokeTrigger('voiceRxUpload'), [invokeTrigger]);
  return { onSelect, disabled: !hasTrigger, isLoading: false, blockers: [] };
}

// ── Kind: newWorkflow (pre-wired for orchestration apps) ────────────────────
// Adding `{kind:'newWorkflow'}` to any app's quickActions config flips the
// menu item on with no further code. Path is derived from the app's
// navigation.homePath so a new orchestration-enabled app gets it for free.
function useNewWorkflowRuntime(): QuickActionRuntime {
  const navigate = useNavigate();
  const appConfig = useCurrentAppConfig();
  const onSelect = useCallback(() => {
    navigate(`${appConfig.navigation.homePath}/campaigns`);
  }, [appConfig.navigation.homePath, navigate]);
  return { onSelect, disabled: false, isLoading: false, blockers: [] };
}

export const QUICK_ACTION_REGISTRY: Record<string, QuickActionDescriptor> = {
  kairaNewChat: {
    label: 'New Chat',
    description: 'Start a new Kaira conversation',
    icon: MessageSquare,
    useResolve: useKairaNewChatRuntime,
  },
  kairaBatchEval: {
    label: 'Batch Evaluation',
    description: 'Evaluate threads from CSV data',
    icon: FileSpreadsheet,
    useResolve: useKairaBatchEvalRuntime,
  },
  insideSalesBatchEval: {
    label: 'Batch Evaluation',
    description: 'Evaluate a selected set of calls',
    icon: FileSpreadsheet,
    useResolve: useInsideSalesBatchEvalRuntime,
  },
  adversarialTest: {
    label: 'Adversarial Test',
    description: 'Run adversarial inputs against the app',
    icon: ShieldAlert,
    useResolve: useAdversarialTestRuntime,
  },
  voiceRxUpload: {
    label: 'Evaluation',
    description: 'Single audio file evaluation',
    icon: FileAudio,
    useResolve: useVoiceRxUploadRuntime,
  },
  newWorkflow: {
    label: 'New Workflow',
    description: 'Open the campaign builder',
    icon: Workflow,
    useResolve: useNewWorkflowRuntime,
  },
};
