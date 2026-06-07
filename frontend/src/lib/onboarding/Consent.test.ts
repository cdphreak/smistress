import { flushSync } from 'svelte';
import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Consent from './Consent.svelte';

test('next is disabled until both boxes are checked, then calls onnext', () => {
  const onnext = vi.fn();
  render(Consent, { onnext });
  screen.getByRole('button', { name: /begin/i }).click();
  expect(onnext).not.toHaveBeenCalled(); // gated by the disabled button
  (screen.getByLabelText(/18/i) as HTMLInputElement).click();
  (screen.getByLabelText(/consent/i) as HTMLInputElement).click();
  flushSync(); // apply batched reactivity so the button un-disables
  screen.getByRole('button', { name: /begin/i }).click();
  expect(onnext).toHaveBeenCalledOnce();
});
