import { render, screen } from '@testing-library/svelte';
import { expect, test, beforeEach } from 'vitest';
import SafeButton from './SafeButton.svelte';
import { safety } from '$lib/stores/safety.svelte';

beforeEach(() => {
  safety.paused = false;
  safety.isHalted = false;
});

test('clicking SAFE pre-halts immediately (client-side) and opens the sheet', async () => {
  render(SafeButton);
  screen.getByRole('button', { name: /safe/i }).click();
  expect(safety.paused).toBe(true); // pre-halt fired before any network
});
