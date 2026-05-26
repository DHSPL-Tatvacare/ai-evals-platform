import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the templates hook — no live network calls per CLAUDE.md test rules.
vi.mock('@/features/orchestration/queries/referenceData', () => ({
  useWatiTemplates: vi.fn(() => ({ data: null })),
}));

import { useWatiTemplates } from '@/features/orchestration/queries/referenceData';
import { TemplateMessagePreview } from '@/features/orchestration/components/preview/TemplateMessagePreview';
import type { VariableMapping } from '@/features/orchestration/components/VariableMappingField';

const mockedTemplates = useWatiTemplates as ReturnType<typeof vi.fn>;

function templateResponse(
  items: Array<{ name: string; body: string; parameters: string[] }>,
) {
  return {
    data: {
      provider: 'wati',
      items: items.map((t) => ({
        name: t.name,
        language: 'en',
        status: 'APPROVED',
        parameters: t.parameters,
        body: t.body,
        bodyOriginal: null,
      })),
      error: null,
    },
  };
}

describe('TemplateMessagePreview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the body with binding chips for static and payload slots', () => {
    mockedTemplates.mockReturnValue(
      templateResponse([
        {
          name: 'welcome',
          body: 'Hi {{1}}, your {{2}} is ready',
          parameters: ['name', 'doc'],
        },
      ]),
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

  it('marks an unbound parameter as not set', () => {
    mockedTemplates.mockReturnValue(
      templateResponse([
        {
          name: 'welcome',
          body: 'Hi {{1}}, your {{2}} is ready',
          parameters: ['name', 'doc'],
        },
      ]),
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
    mockedTemplates.mockReturnValue(
      templateResponse([
        { name: 'welcome', body: '', parameters: ['name', 'doc'] },
      ]),
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

  it('shows the empty state when no template matches', () => {
    mockedTemplates.mockReturnValue(
      templateResponse([
        { name: 'other', body: 'Hi {{1}}', parameters: ['name'] },
      ]),
    );

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
