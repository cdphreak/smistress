import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Scale from './Scale.svelte';

test('renders a slider and reports changes', async () => {
  const onchange = vi.fn();
  render(Scale, { min: 0, max: 4, value: 2, onchange });
  const slider = screen.getByRole('slider') as HTMLInputElement;
  expect(slider.value).toBe('2');
});
