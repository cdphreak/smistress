import { flushSync } from 'svelte';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Toys from './Toys.svelte';

test('selecting a prefilled type + name submits the toy', async () => {
  const onnext = vi.fn();
  render(Toys, { types: ['vibrator', 'chastity_cage'], onnext });

  // The dropdown is fed by the controlled vocabulary (labels de-underscored).
  expect(screen.getByRole('option', { name: 'chastity cage' })).toBeInTheDocument();

  await fireEvent.input(screen.getByLabelText('Name'), { target: { value: 'Apex' } });
  await fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'chastity_cage' } });
  flushSync();

  screen.getByRole('button', { name: /add & continue/i }).click();
  expect(onnext).toHaveBeenCalledWith({
    name: 'Apex',
    type: 'chastity_cage',
    intiface_capable: false
  });
});

test('skip submits null', () => {
  const onnext = vi.fn();
  render(Toys, { types: ['vibrator'], onnext });
  screen.getByRole('button', { name: /skip/i }).click();
  expect(onnext).toHaveBeenCalledWith(null);
});
