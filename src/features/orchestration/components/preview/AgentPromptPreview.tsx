import { Fragment } from 'react';

import { useAgentIntrospection } from '@/features/orchestration/queries/referenceData';

interface Props {
  config: Record<string, unknown>;
}

/** Matches {token} placeholders in agent prompts. */
const TOKEN_RE = /\{([^{}]+)\}/g;

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-full items-center justify-center p-4 text-center text-xs text-[var(--text-secondary)]">
      {message}
    </div>
  );
}

/** Inline pill for a {token} placeholder. */
function TokenPill({ name }: { name: string }) {
  return (
    <span className="mx-0.5 inline-flex items-center rounded-full border border-[color-mix(in_srgb,var(--interactive-primary)_35%,transparent)] bg-[color-mix(in_srgb,var(--interactive-primary)_14%,var(--bg-primary))] px-1.5 py-0.5 align-baseline font-mono text-[11px] text-[var(--text-primary)]">
      {`{${name}}`}
    </span>
  );
}

/** Split text on {token} patterns and interleave with pill spans. */
function renderPrompt(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  TOKEN_RE.lastIndex = 0;
  let key = 0;
  while ((match = TOKEN_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      out.push(<Fragment key={`t-${key}`}>{text.slice(lastIndex, match.index)}</Fragment>);
    }
    out.push(<TokenPill key={`p-${key}`} name={match[1]} />);
    lastIndex = match.index + match[0].length;
    key += 1;
  }
  if (lastIndex < text.length) {
    out.push(<Fragment key={`t-${key}`}>{text.slice(lastIndex)}</Fragment>);
  }
  return out;
}

/** Read-only scrollable agent prompt preview with {token} highlighting. */
export function AgentPromptPreview({ config }: Props) {
  const connectionId = typeof config.connection_id === 'string' ? config.connection_id : undefined;
  const agentId = typeof config.agent_id === 'string' ? config.agent_id : undefined;

  const { data, error } = useAgentIntrospection(connectionId, agentId);

  if (!agentId) {
    return <EmptyState message="Select an agent to preview its prompt." />;
  }

  const prompt = data?.prompt ?? '';
  const welcomeMessage = data?.welcomeMessage ?? '';
  const softError = error instanceof Error ? error.message : (data?.error ?? null);

  if (!prompt && !welcomeMessage) {
    if (softError) {
      return (
        <EmptyState message={`Could not load agent prompt: ${softError}`} />
      );
    }
    if (data) {
      return <EmptyState message="No prompt configured for this agent." />;
    }
    // Still loading
    return <EmptyState message="Loading agent prompt…" />;
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-4 gap-4">
      <span className="text-[10.5px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">
        Agent prompt
      </span>

      {prompt.trim().length > 0 && (
        <div className="whitespace-pre-wrap break-words rounded-[var(--radius-default)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-[12.5px] leading-relaxed text-[var(--text-primary)]">
          {renderPrompt(prompt)}
        </div>
      )}

      {welcomeMessage.trim().length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
            Welcome message
          </span>
          <div className="whitespace-pre-wrap break-words rounded-[var(--radius-default)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-[12.5px] leading-relaxed text-[var(--text-primary)]">
            {renderPrompt(welcomeMessage)}
          </div>
        </div>
      )}

      {softError && (
        <p className="text-xs text-[var(--color-error)]">{softError}</p>
      )}
    </div>
  );
}
