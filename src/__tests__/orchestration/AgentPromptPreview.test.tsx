import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the hook — no live network calls per CLAUDE.md test rules.
vi.mock('@/features/orchestration/queries/referenceData', () => ({
  useAgentIntrospection: vi.fn(),
  useWatiTemplates: vi.fn(() => ({ data: null })),
  useBolnaAgents: vi.fn(() => ({ data: null, isFetching: false, error: null, refresh: vi.fn() })),
  useProviderPhoneNumbers: vi.fn(() => ({ data: null, isFetching: false, error: null, refresh: vi.fn() })),
}));

import { useAgentIntrospection } from '@/features/orchestration/queries/referenceData';
import { AgentPromptPreview } from '@/features/orchestration/components/preview/AgentPromptPreview';

const mockedHook = useAgentIntrospection as ReturnType<typeof vi.fn>;

function agentResponse(prompt: string, welcomeMessage = '', error: string | null = null) {
  return {
    data: {
      provider: 'bolna',
      variables: [],
      prompt,
      welcomeMessage,
      error,
    },
    error: null,
  };
}

describe('AgentPromptPreview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state when no agentId is set', () => {
    mockedHook.mockReturnValue({ data: undefined, error: null });
    render(<AgentPromptPreview config={{ connection_id: 'conn-1' }} />);
    expect(screen.getByText(/Select an agent to preview/i)).toBeInTheDocument();
  });

  it('renders the prompt text with {token} highlighted when prompt contains tokens', () => {
    mockedHook.mockReturnValue(
      agentResponse('Hello {name}, your plan is {plan}.'),
    );
    render(
      <AgentPromptPreview
        config={{ connection_id: 'conn-1', agent_id: 'agt_001' }}
      />,
    );

    // Plain text segments should appear
    expect(screen.getByText(/Hello/)).toBeInTheDocument();
    expect(screen.getByText(/your plan is/)).toBeInTheDocument();
    // Tokens render as highlighted pills with braces
    expect(screen.getByText('{name}')).toBeInTheDocument();
    expect(screen.getByText('{plan}')).toBeInTheDocument();
  });

  it('renders welcome message section when welcomeMessage is present', () => {
    mockedHook.mockReturnValue(
      agentResponse('System prompt text.', 'Hi {patient}, welcome!'),
    );
    render(
      <AgentPromptPreview
        config={{ connection_id: 'conn-1', agent_id: 'agt_001' }}
      />,
    );

    expect(screen.getByText(/System prompt text/)).toBeInTheDocument();
    expect(screen.getByText(/Welcome message/i)).toBeInTheDocument();
    expect(screen.getByText('{patient}')).toBeInTheDocument();
  });

  it('shows loading state before data arrives', () => {
    // Hook returns no data yet (still fetching)
    mockedHook.mockReturnValue({ data: undefined, error: null });
    render(
      <AgentPromptPreview
        config={{ connection_id: 'conn-1', agent_id: 'agt_001' }}
      />,
    );
    expect(screen.getByText(/Loading agent prompt/i)).toBeInTheDocument();
  });

  it('shows empty state when prompt and welcome message are both empty', () => {
    mockedHook.mockReturnValue(agentResponse('', ''));
    render(
      <AgentPromptPreview
        config={{ connection_id: 'conn-1', agent_id: 'agt_001' }}
      />,
    );
    expect(screen.getByText(/No prompt configured/i)).toBeInTheDocument();
  });

  it('surfaces soft error from data.error subtly alongside content', () => {
    mockedHook.mockReturnValue(
      agentResponse('Good prompt.', '', 'Could not fetch variables'),
    );
    render(
      <AgentPromptPreview
        config={{ connection_id: 'conn-1', agent_id: 'agt_001' }}
      />,
    );
    expect(screen.getByText(/Good prompt/)).toBeInTheDocument();
    expect(screen.getByText(/Could not fetch variables/)).toBeInTheDocument();
  });

  it('surfaces hard error from hook error as empty state', () => {
    mockedHook.mockReturnValue({
      data: undefined,
      error: new Error('Network failure'),
    });
    render(
      <AgentPromptPreview
        config={{ connection_id: 'conn-1', agent_id: 'agt_001' }}
      />,
    );
    expect(screen.getByText(/Could not load agent prompt.*Network failure/i)).toBeInTheDocument();
  });
});
