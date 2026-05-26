import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { StructuredRequestBodyEditor } from '@/features/orchestration/components/editors/StructuredRequestBodyEditor';

function getTextarea(): HTMLTextAreaElement {
  // The component renders both a <textarea> (the JSON body) and a helper
  // <input> inside the disclosure — both have role=textbox in jsdom. We
  // want the textarea specifically.
  const candidates = screen.getAllByRole('textbox');
  const textarea = candidates.find(
    (el): el is HTMLTextAreaElement => el.tagName === 'TEXTAREA',
  );
  if (!textarea) {
    throw new Error('expected a <textarea> in StructuredRequestBodyEditor');
  }
  return textarea;
}

describe('StructuredRequestBodyEditor', () => {
  it('serializes the structured body to formatted JSON in the textarea', () => {
    const onChange = vi.fn();
    render(
      <StructuredRequestBodyEditor
        value={{
          name: { $payload: 'first_name' },
          static: 'value',
        }}
        onChange={onChange}
      />,
    );
    const textarea = getTextarea();
    expect(textarea.value).toContain('"$payload"');
    expect(textarea.value).toContain('first_name');
  });

  it('parses valid JSON edits and persists them through onChange', () => {
    const onChange = vi.fn();
    render(<StructuredRequestBodyEditor value={{}} onChange={onChange} />);
    const textarea = getTextarea();
    fireEvent.change(textarea, {
      target: {
        value: '{ "x": 1, "ref": { "$payload": "y" } }',
      },
    });
    expect(onChange).toHaveBeenCalledWith({
      x: 1,
      ref: { $payload: 'y' },
    });
  });

  it('keeps the textarea editable when JSON is invalid and surfaces the error', () => {
    const onChange = vi.fn();
    render(<StructuredRequestBodyEditor value={{}} onChange={onChange} />);
    const textarea = getTextarea();
    fireEvent.change(textarea, { target: { value: '{ not json' } });
    expect(textarea.value).toBe('{ not json');
    expect(screen.getByText(/JSON parse error/)).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('does not pretty-reformat the text when the parsed value round-trips back', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <StructuredRequestBodyEditor value={{}} onChange={onChange} />,
    );
    const textarea = getTextarea();
    // User types compact JSON; the editor must not normalize whitespace.
    fireEvent.change(textarea, { target: { value: '{"x":1}' } });
    expect(onChange).toHaveBeenLastCalledWith({ x: 1 });
    // Parent persists the parsed value and feeds it straight back.
    rerender(<StructuredRequestBodyEditor value={{ x: 1 }} onChange={onChange} />);
    expect(getTextarea().value).toBe('{"x":1}');
  });
});
