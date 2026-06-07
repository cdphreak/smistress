import { beforeEach, expect, test, vi } from 'vitest';

// Mock the api layer so the store can be tested without a network.
vi.mock('$lib/api/safety', () => ({
  safeword: vi.fn(async () => ({
    scene_halted: true, denial_lifted: 2, merit_penalty: 0,
    aftercare: 'rest', message: 'stopping now'
  })),
  resume: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false })),
  getSafety: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false }))
}));

import { safety } from './safety.svelte';
import { session } from './session.svelte';

beforeEach(() => {
  localStorage.clear();
  session.setProfileId('p1');
  safety.paused = false;
  safety.isHalted = false;
  safety.receipt = null;
});

test('preHalt sets paused client-side with no network call', async () => {
  const api = await import('$lib/api/safety');
  safety.preHalt();
  expect(safety.paused).toBe(true);
  expect(api.safeword).not.toHaveBeenCalled(); // pre-halt is pure client
});

test('confirmStop posts safeword and records the receipt', async () => {
  const api = await import('$lib/api/safety');
  await safety.confirmStop();
  expect(api.safeword).toHaveBeenCalledWith('p1');
  expect(safety.isHalted).toBe(true);
  expect(safety.receipt?.message).toBe('stopping now');
});

test('resumeScene clears halt and receipt', async () => {
  await safety.confirmStop();
  await safety.resumeScene();
  expect(safety.isHalted).toBe(false);
  expect(safety.paused).toBe(false);
  expect(safety.receipt).toBeNull();
});
