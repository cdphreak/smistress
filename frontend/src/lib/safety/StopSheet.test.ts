import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/safety', () => ({
  safeword: vi.fn(async () => ({
    scene_halted: true, denial_lifted: 1, merit_penalty: 0,
    aftercare: 'tea and quiet', message: "Okay — we're stopping now."
  })),
  resume: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false })),
  getSafety: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false }))
}));

import StopSheet from './StopSheet.svelte';
import { safety } from '$lib/stores/safety.svelte';
import { session } from '$lib/stores/session.svelte';

beforeEach(() => {
  session.setProfileId('p1');
  safety.paused = false;
  safety.isHalted = false;
  safety.receipt = null;
});

test('open sheet shows the confirm prompt; confirming shows the calm receipt', async () => {
  safety.preHalt(); // sheet is shown when paused
  render(StopSheet);
  expect(screen.getByText(/stop everything/i)).toBeInTheDocument();

  screen.getByRole('button', { name: /stop everything/i }).click();
  // allow the awaited confirmStop + reactive flush
  await vi.waitFor(() => {
    expect(screen.getByText(/stopping now/i)).toBeInTheDocument();
  });
  expect(screen.getByText(/tea and quiet/i)).toBeInTheDocument();
  expect(safety.isHalted).toBe(true);
});

test('nothing renders when not paused', () => {
  render(StopSheet);
  expect(screen.queryByText(/stop everything/i)).not.toBeInTheDocument();
});
