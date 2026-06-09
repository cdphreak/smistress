import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/dossier', () => ({
  getDossier: vi.fn(async () => ({
    rank: 'adept',
    merit: 50,
    tokens: 3,
    disposition: {
      band: 'neutral',
      line: 'neutral · measured — strong standing',
      reason: 'x',
      standing: 60
    },
    active_task: null,
    debt: 0,
    chastity: { locked: false, ends_at: null, seconds_remaining: 0 }
  }))
}));

import { dossier } from './dossier.svelte';
import { session } from './session.svelte';

beforeEach(() => session.setProfileId('p1'));

test('refresh loads live status', async () => {
  await dossier.refresh();
  expect(dossier.data?.rank).toBe('adept');
  expect(dossier.data?.disposition.line).toContain('measured');
});
