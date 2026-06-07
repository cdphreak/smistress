import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import KinkSheet from './KinkSheet.svelte';

test('rates a kink and submits non-NA entries', async () => {
  const onnext = vi.fn();
  render(KinkSheet, { kinks: ['bondage', 'spanking'], onnext });
  // each row defaults to N-A; rate the first row Hard-limit
  const hardButtons = screen.getAllByRole('button', { name: 'Hard' });
  hardButtons[0].click();
  screen.getByRole('button', { name: /next/i }).click();
  expect(onnext).toHaveBeenCalledOnce();
  const entries = onnext.mock.calls[0][0];
  expect(entries).toEqual([{ kink: 'bondage', rating: 'hard_limit' }]); // NA rows omitted
});
