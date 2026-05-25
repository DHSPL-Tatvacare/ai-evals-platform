import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { SampleSizeField } from './SampleSizeField';

describe('SampleSizeField', () => {
  it('emits null when strategy set to No limit', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SampleSizeField limit={100} strategy="random" onChange={onChange} />);
    // Two comboboxes present (strategy + size); target the strategy one by its current label.
    await user.click(screen.getByRole('combobox', { name: 'Random sample' }));
    await user.click(await screen.findByRole('option', { name: 'No limit' }));
    expect(onChange).toHaveBeenCalledWith({ limit: null, strategy: 'random' });
  });

  it('defaults to 100 when a strategy is first chosen', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SampleSizeField limit={null} strategy="random" onChange={onChange} />);
    // limit null => only the strategy combobox renders (label 'No limit').
    await user.click(screen.getByRole('combobox', { name: 'No limit' }));
    await user.click(await screen.findByRole('option', { name: 'Random sample' }));
    expect(onChange).toHaveBeenCalledWith({ limit: 100, strategy: 'random' });
  });

  it('forwards a chosen preset size', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SampleSizeField limit={100} strategy="first" onChange={onChange} />);
    // Target the SIZE combobox by its current value label '100' (strategy one is 'First N').
    await user.click(screen.getByRole('combobox', { name: '100' }));
    await user.click(await screen.findByRole('option', { name: '1,000' }));
    expect(onChange).toHaveBeenCalledWith({ limit: 1000, strategy: 'first' });
  });
});
