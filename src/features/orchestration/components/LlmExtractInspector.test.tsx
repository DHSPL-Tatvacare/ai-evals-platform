import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { LlmExtractInspector } from './LlmExtractInspector';

vi.mock('@/hooks', () => ({
  useCurrentAppId: () => 'inside-sales',
}));

function renderInspector(overrides: Partial<Parameters<typeof LlmExtractInspector>[0]> = {}) {
  const onChange = vi.fn();
  const onClose = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <LlmExtractInspector
        value={{
          prompt: 'Classify {{last_message}}',
          output_schema: [
            { key: 'sentiment', type: 'enum' },
            { key: 'confidence', type: 'number' },
          ],
          output_namespace: 'analysis',
          concurrency: 3,
          inter_call_delay: 0,
        }}
        onChange={onChange}
        workflowType="crm"
        displayLabel="AI Agent"
        nodeType="llm.extract"
        onClose={onClose}
        {...overrides}
      />
    </QueryClientProvider>,
  );
  return { onChange, onClose };
}

describe('LlmExtractInspector', () => {
  it('renders the AI Agent title and the llm.extract type', () => {
    renderInspector();
    expect(screen.getByText('AI Agent')).toBeInTheDocument();
    expect(screen.getByText('llm.extract')).toBeInTheDocument();
  });

  it('renders all three panes (Input · Configure · Test)', () => {
    renderInspector();
    expect(screen.getByText('Input')).toBeInTheDocument();
    expect(screen.getByText('Configure')).toBeInTheDocument();
    expect(screen.getByText('Test')).toBeInTheDocument();
  });

  it('edits the prompt and reports the change', () => {
    const { onChange } = renderInspector();
    const prompt = screen.getByPlaceholderText(/classify the sentiment/i);
    fireEvent.change(prompt, { target: { value: 'New prompt {{first_name}}' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ prompt: 'New prompt {{first_name}}' }),
    );
  });

  it('shows the configured output fields as a read-only preview', () => {
    renderInspector();
    expect(screen.getByText('sentiment')).toBeInTheDocument();
    expect(screen.getByText('confidence')).toBeInTheDocument();
  });

  it('disables Generate-with-AI and Edit-schema in this commit', () => {
    renderInspector();
    expect(screen.getByRole('button', { name: /generate with ai/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /edit schema/i })).toBeDisabled();
  });

  it('reveals the four advanced fields and edits Save results as', () => {
    const { onChange } = renderInspector();
    fireEvent.click(screen.getByRole('button', { name: /advanced/i }));
    const namespace = screen.getByDisplayValue('analysis');
    fireEvent.change(namespace, { target: { value: 'result' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ output_namespace: 'result' }),
    );
    // Context template + concurrency + delay are the other advanced fields.
    expect(screen.getByText(/context template/i)).toBeInTheDocument();
    expect(screen.getByText(/concurrency/i)).toBeInTheDocument();
  });

  it('renders the Test pane Run control as disabled (inert scaffold)', () => {
    renderInspector();
    expect(screen.getByRole('button', { name: /^run/i })).toBeDisabled();
  });

  it('invokes onClose from the header close button', () => {
    const { onClose } = renderInspector();
    fireEvent.click(screen.getByRole('button', { name: /close inspector/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
