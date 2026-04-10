import { useEffect, useCallback, useRef, useState } from 'react';
import { Sparkles, X, Minus, Plus, GripVertical } from 'lucide-react';
import { cn } from '@/utils/cn';
import { useAppStore } from '@/stores';
import { useLLMSettingsStore, hasProviderCredentials } from '@/stores/llmSettingsStore';
import { useChatWidgetStore } from './useChatWidget';
import { ProviderToggle } from './ProviderToggle';
import { ChatMessages } from './ChatMessages';
import { ChatInput } from './ChatInput';
import type { ChatProvider, ChatWidgetConfig } from './types';

export function ChatWidget() {
  const currentApp = useAppStore((s) => s.currentApp);
  const appConfig = useAppStore((s) => s.getAppConfig(currentApp));
  const chatConfig: ChatWidgetConfig = (appConfig as any)?.chat ?? {};

  const open = useChatWidgetStore((s) => s.open);
  const toggle = useChatWidgetStore((s) => s.toggle);
  const provider = useChatWidgetStore((s) => s.provider);
  const locked = useChatWidgetStore((s) => s.locked);
  const messages = useChatWidgetStore((s) => s.messages);
  const status = useChatWidgetStore((s) => s.status);
  const defaults = useChatWidgetStore((s) => s.defaults);
  const setProvider = useChatWidgetStore((s) => s.setProvider);
  const send = useChatWidgetStore((s) => s.send);
  const reset = useChatWidgetStore((s) => s.reset);
  const loadDefaults = useChatWidgetStore((s) => s.loadDefaults);

  // Vertical drag state
  const [bottomOffset, setBottomOffset] = useState(24);
  const dragRef = useRef<{ startY: number; startBottom: number } | null>(null);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { startY: e.clientY, startBottom: bottomOffset };

    const handleMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const delta = dragRef.current.startY - ev.clientY;
      const newBottom = Math.max(8, Math.min(window.innerHeight - 100, dragRef.current.startBottom + delta));
      setBottomOffset(newBottom);
    };

    const handleUp = () => {
      dragRef.current = null;
      document.removeEventListener('mousemove', handleMove);
      document.removeEventListener('mouseup', handleUp);
    };

    document.addEventListener('mousemove', handleMove);
    document.addEventListener('mouseup', handleUp);
  }, [bottomOffset]);

  useEffect(() => {
    if (!defaults) void loadDefaults();
  }, [defaults, loadDefaults]);

  const geminiApiKey = useLLMSettingsStore((s) => s.geminiApiKey);
  const openaiApiKey = useLLMSettingsStore((s) => s.openaiApiKey);
  const azureApiKey = useLLMSettingsStore((s) => s.azureOpenaiApiKey);
  const azureEndpoint = useLLMSettingsStore((s) => s.azureOpenaiEndpoint);
  const saConfigured = useLLMSettingsStore((s) => s._serviceAccountConfigured);

  const credState = { geminiApiKey, openaiApiKey, azureOpenaiApiKey: azureApiKey, azureOpenaiEndpoint: azureEndpoint, anthropicApiKey: '', _serviceAccountConfigured: saConfigured };
  const providerDisabled: Record<ChatProvider, boolean> = {
    gemini: !hasProviderCredentials('gemini', credState),
    openai: !hasProviderCredentials('openai', credState) && !hasProviderCredentials('azure_openai', credState),
  };

  const handleSend = useCallback(
    (text: string) => void send(text, currentApp),
    [send, currentApp],
  );

  const promptTemplates = chatConfig.promptTemplates ?? [];

  if (chatConfig.enabled === false) return null;

  // Collapsed bubble
  if (!open) {
    return (
      <button
        onClick={toggle}
        style={{ bottom: bottomOffset }}
        className={cn(
          'fixed right-6 z-[var(--z-overlay)]',
          'flex h-14 w-14 items-center justify-center rounded-full',
          'bg-[var(--color-brand-primary)] text-white shadow-lg',
          'hover:bg-[var(--color-brand-primary-hover)] hover:scale-105',
          'transition-all duration-150',
        )}
        aria-label="Open AI Assistant"
      >
        <Sparkles className="h-6 w-6" />
      </button>
    );
  }

  // Expanded widget
  const canSend = !!provider && !providerDisabled[provider] && status !== 'sending' && !!defaults;

  return (
    <div
      style={{ bottom: bottomOffset, resize: 'both', overflow: 'hidden', direction: 'rtl' }}
      className={cn(
        'fixed right-6 z-[var(--z-overlay)]',
        'flex flex-col rounded-2xl bg-[var(--bg-primary)] shadow-2xl',
        'border border-[var(--border-default)]',
        'w-[420px] h-[560px] min-w-[360px] min-h-[400px] max-w-[600px] max-h-[80vh]',
      )}
    >
      <div style={{ direction: 'ltr' }} className="flex flex-col h-full">
        {/* Header with drag handle */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border-default)]">
          <div className="flex items-center gap-2">
            {/* Drag handle */}
            <div
              onMouseDown={handleDragStart}
              className="flex h-7 w-4 items-center justify-center cursor-grab active:cursor-grabbing text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              title="Drag to reposition"
            >
              <GripVertical className="h-3.5 w-3.5" />
            </div>
            <div className="flex h-7 w-7 items-center justify-center rounded bg-[var(--color-brand-accent)]">
              <Sparkles className="h-3.5 w-3.5 text-[var(--color-brand-primary)]" />
            </div>
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">AI Assistant</h3>
            <span className="text-[10px] font-medium text-[var(--color-brand-primary)] bg-[var(--color-brand-accent)] px-1.5 py-0.5 rounded">
              {currentApp}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={reset}
              title="New chat"
              className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={toggle}
              title="Minimize"
              className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => { toggle(); reset(); }}
              title="Close"
              className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <ProviderToggle
          selected={provider}
          onSelect={setProvider}
          locked={locked}
          disabled={providerDisabled}
        />

        <ChatMessages
          messages={messages}
          status={status}
          promptTemplates={promptTemplates}
          onPromptSelect={handleSend}
        />

        <ChatInput
          onSend={handleSend}
          disabled={!canSend}
          placeholder={
            !provider
              ? 'Select a provider to start...'
              : !defaults
                ? 'Loading...'
                : `Ask about ${currentApp}...`
          }
        />
      </div>
    </div>
  );
}
