import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the introspection hook — no live network calls per CLAUDE.md test rules.
vi.mock('@/features/orchestration/queries/referenceData', () => ({
  useTemplateIntrospection: vi.fn(() => ({ data: null })),
}));

import { useTemplateIntrospection } from '@/features/orchestration/queries/referenceData';
import { TemplateMessagePreview } from '@/features/orchestration/components/preview/TemplateMessagePreview';
import type { VariableMapping } from '@/features/orchestration/components/VariableMappingField';

const mockedIntrospection = useTemplateIntrospection as ReturnType<typeof vi.fn>;

function introspectionResponse(template: { body: string; parameters: string[] } | null) {
  return {
    data: template
      ? {
          provider: 'wati',
          variables: template.parameters,
          prompt: '',
          welcomeMessage: '',
          body: template.body,
          bodyOriginal: null,
          error: null,
        }
      : null,
  };
}

describe('TemplateMessagePreview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the body with binding chips for static and payload slots', () => {
    mockedIntrospection.mockReturnValue(
      introspectionResponse({
        body: 'Hi {{1}}, your {{2}} is ready',
        parameters: ['name', 'doc'],
      }),
    );
    const mappings: VariableMapping[] = [
      { agent_variable: 'name', source_kind: 'static', static_value: 'Priya' },
      { agent_variable: 'doc', source_kind: 'payload', payload_field: 'first_name' },
    ];

    render(
      <TemplateMessagePreview
        connectionId="conn-wati"
        templateName="welcome"
        variableMappings={mappings}
      />,
    );

    expect(screen.getByText(/Hi/)).toBeInTheDocument();
    expect(screen.getByText(/is ready/)).toBeInTheDocument();
    expect(screen.getByText(/Priya/)).toBeInTheDocument();
    expect(screen.getByText(/first_name/)).toBeInTheDocument();
  });

  it('renders named placeholders as chips, not literal {{name}} text', () => {
    mockedIntrospection.mockReturnValue(
      introspectionResponse({
        body: 'Hi {{patient name}}, your {{Included plan}} is active',
        parameters: ['patient name', 'Included plan'],
      }),
    );
    const mappings: VariableMapping[] = [
      { agent_variable: 'patient name', source_kind: 'payload', payload_field: 'first_name' },
      { agent_variable: 'Included plan', source_kind: 'static', static_value: 'GoldCare' },
    ];

    render(
      <TemplateMessagePreview
        connectionId="conn-wati"
        templateName="rnr_call"
        variableMappings={mappings}
      />,
    );

    expect(screen.getByText(/first_name/)).toBeInTheDocument();
    expect(screen.getByText(/GoldCare/)).toBeInTheDocument();
    // The named placeholder must be replaced by a chip, never rendered raw.
    expect(screen.queryByText(/\{\{patient name\}\}/)).not.toBeInTheDocument();
  });

  it('marks an unbound parameter as not set', () => {
    mockedIntrospection.mockReturnValue(
      introspectionResponse({
        body: 'Hi {{1}}, your {{2}} is ready',
        parameters: ['name', 'doc'],
      }),
    );
    const mappings: VariableMapping[] = [
      { agent_variable: 'name', source_kind: 'static', static_value: 'Priya' },
    ];

    render(
      <TemplateMessagePreview
        connectionId="conn-wati"
        templateName="welcome"
        variableMappings={mappings}
      />,
    );

    expect(screen.getByText(/not set/i)).toBeInTheDocument();
  });

  it('falls back to a slot list when the body is empty', () => {
    mockedIntrospection.mockReturnValue(
      introspectionResponse({ body: '', parameters: ['name', 'doc'] }),
    );
    const mappings: VariableMapping[] = [
      { agent_variable: 'name', source_kind: 'static', static_value: 'Priya' },
      { agent_variable: 'doc', source_kind: 'payload', payload_field: 'first_name' },
    ];

    render(
      <TemplateMessagePreview
        connectionId="conn-wati"
        templateName="welcome"
        variableMappings={mappings}
      />,
    );

    expect(screen.getByText('name')).toBeInTheDocument();
    expect(screen.getByText('doc')).toBeInTheDocument();
    expect(screen.getByText(/Priya/)).toBeInTheDocument();
    expect(screen.getByText(/first_name/)).toBeInTheDocument();
  });

  it('shows the empty state when the template has not loaded', () => {
    mockedIntrospection.mockReturnValue(introspectionResponse(null));

    render(
      <TemplateMessagePreview
        connectionId="conn-wati"
        templateName="welcome"
        variableMappings={[]}
      />,
    );

    expect(screen.getByText(/Select a template to preview/i)).toBeInTheDocument();
  });
});
