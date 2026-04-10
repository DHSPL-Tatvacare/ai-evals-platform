import { useEffect, useCallback } from 'react';
import { MessageCircle, X, Minus, Plus } from 'lucide-react';
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

  if (!open) {
    return (
      <button
        onClick={toggle}
        className={cn(
          'fixed bottom-6 right-6 z-[var(--z-overlay)]',
          'flex h-14 w-14 items-center justify-center rounded-full',
          'bg-[var(--color-brand-primary)] text-white shadow-lg',
          'hover:bg-[var(--color-brand-primary-hover)] hover:scale-105',
          'transition-all duration-150',
        )}
        aria-label="Open AI Assistant"
      >
        <MessageCircle className="h-6 w-6" />
      </button>
    );
  }

  const canSend = !!provider && !providerDisabled[provider] && status !== 'sending' && !!defaults;

  return (
    <div
      className={cn(
        'fixed bottom-6 right-6 z-[var(--z-overlay)]',
        'flex flex-col overflow-hidden rounded-2xl bg-[var(--bg-primary)] shadow-2xl',
        'border border-[var(--border-default)]',
        'w-[420px] h-[560px] min-w-[360px] min-h-[400px] max-w-[600px] max-h-[80vh]',
      )}
      style={{ resize: 'both', overflow: 'hidden', direction: 'rtl' }}
    >
      <div style={{ direction: 'ltr' }} className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border-default)]">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded bg-[var(--color-brand-accent)]">
              <MessageCircle className="h-3.5 w-3.5 text-[var(--color-brand-primary)]" />
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
