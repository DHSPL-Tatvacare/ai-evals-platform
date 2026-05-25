import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { NumberPresetSelect } from './NumberPresetSelect';

const PRESETS = [10, 100, 1000, 10000];

describe('NumberPresetSelect', () => {
  it('emits the chosen preset', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<NumberPresetSelect value={null} onChange={onChange} presets={PRESETS} min={1} max={10000} />);
    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: '100' }));
    expect(onChange).toHaveBeenCalledWith(100);
  });

  it('reveals a custom input and emits the typed number', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<NumberPresetSelect value={null} onChange={onChange} presets={PRESETS} min={1} max={10000} />);
    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: 'Custom…' }));
    fireEvent.change(screen.getByPlaceholderText('1–10000'), { target: { value: '250' } });
    expect(onChange).toHaveBeenCalledWith(250);
  });

  it('clamps a typed value to max', () => {
    const onChange = vi.fn();
    render(<NumberPresetSelect value={250} onChange={onChange} presets={PRESETS} min={1} max={10000} />);
    fireEvent.change(screen.getByPlaceholderText('1–10000'), { target: { value: '99999' } });
    expect(onChange).toHaveBeenCalledWith(10000);
  });
});
