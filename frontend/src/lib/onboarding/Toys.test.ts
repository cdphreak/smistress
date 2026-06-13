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
    intiface_capable: false,
    noise: false,
    visibility: false,
    discreet_capable: false
  });
});

test('skip submits null', () => {
  const onnext = vi.fn();
  render(Toys, { types: ['vibrator'], onnext });
  screen.getByRole('button', { name: /skip/i }).click();
  expect(onnext).toHaveBeenCalledWith(null);
});

test('emits the three discreetness flags', async () => {
  const onnext = vi.fn();
  render(Toys, { types: ['vibrator'], onnext });

  await fireEvent.input(screen.getByLabelText('Name'), { target: { value: 'Apex' } });
  await fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'vibrator' } });
  await fireEvent.click(screen.getByLabelText(/discreet-capable/i));
  await fireEvent.click(screen.getByLabelText(/makes noise/i));
  flushSync();

  screen.getByRole('button', { name: /add & continue/i }).click();
  expect(onnext).toHaveBeenCalledWith({
    name: 'Apex',
    type: 'vibrator',
    intiface_capable: false,
    noise: true,
    visibility: false,
    discreet_capable: true
  });
});

test('prefills from initial for editing', () => {
  const onnext = vi.fn();
  render(Toys, {
    types: ['vibrator'],
    onnext,
    initial: { name: 'Old', type: 'vibrator', intiface_capable: false, noise: true, visibility: false, discreet_capable: false }
  });
  expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('Old');
  expect((screen.getByLabelText(/makes noise/i) as HTMLInputElement).checked).toBe(true);
  expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
});
